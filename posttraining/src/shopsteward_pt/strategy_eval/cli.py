"""Command line for generating cases, running strategy batches and reporting.

Run from `posttraining/` with the main project environment (it needs LangGraph):
    $env:PYTHONPATH = "src"; python -m shopsteward_pt.strategy_eval run --help
"""

import argparse
import asyncio
import json
from pathlib import Path

from . import _paths  # noqa: F401
from .cases import load_dataset, write_dataset
from .runner import (
    OracleModel,
    Retrying,
    gate_report,
    load_records,
    markdown,
    run_batch,
    summarize,
)


def _model(args, fixtures):
    from shopsteward_agent.context import ModelProfile

    profile = ModelProfile(
        profile_id="eval-" + args.model,
        model_id=args.model,
        max_input_tokens=128000,
        max_output_tokens=2048,
        timeout_s=60,
    )
    if args.fake:
        return OracleModel(fixtures), profile.model_copy(update={"model_id": "oracle-fake"})
    from shopsteward_agent.model import OpenAIModel

    return (
        Retrying(
            OpenAIModel(
                base_url=args.base_url, model=args.model, key_file=args.key_file, profile=profile
            )
        ),
        profile,
    )


def _evolve(args):
    from shopsteward_agent.cases import load_bundle, make_bundle, save_bundle
    from shopsteward_agent.context import ModelProfile
    from shopsteward_agent.model import OpenAIModel

    from .evolve import evolve

    def client(model_id, output, timeout):
        profile = ModelProfile(
            profile_id="evolve-" + model_id,
            model_id=model_id,
            max_input_tokens=128000,
            max_output_tokens=output,
            timeout_s=timeout,
        )
        return (
            Retrying(
                OpenAIModel(
                    base_url=args.base_url, model=model_id, key_file=args.key_file, profile=profile
                )
            ),
            profile,
        )

    base = load_bundle(args.bundle, directory=args.bundle_dir)
    pairs = [
        pair
        for pair in load_dataset(args.cases)
        if pair[1]["partition"] in ("evo-train", "evo-val")
    ]
    task_model, task_profile = client(args.model, 2048, 60)
    reflection_model, reflection_profile = client(args.reflection_model, 4096, 120)
    components = args.components.split(",")
    best, result, adapter = evolve(
        pairs,
        base=base,
        strategy=args.strategy,
        task_model=task_model,
        task_profile=task_profile,
        reflection_model=reflection_model,
        components=components,
        max_metric_calls=args.max_metric_calls,
        run_dir=args.run_dir,
        seed=args.seed,
        minibatch=args.minibatch,
        parallel=args.parallel,
    )
    scores = list(result.val_aggregate_scores)
    summary = {
        "strategy": args.strategy,
        "components": components,
        "seed_val_score": scores[0],
        "best_val_score": max(scores),
        "candidates": len(scores),
        "val_scores": scores,
        "metric_calls": result.total_metric_calls,
        "changed": [name for name in components if best[name] != base.components[name]],
        "evaluations": adapter.log,
    }
    if summary["changed"]:
        bundle = make_bundle(
            args.revision,
            {**base.components, **best},
            parent_revision=base.revision,
            provenance={
                "origin": "gepa",
                "optimizer_version": "0.1.4",
                "seed": args.seed,
                "strategy": args.strategy,
                "max_metric_calls": args.max_metric_calls,
                "task_profile": task_profile.model_dump(mode="json"),
                "reflection_profile": reflection_profile.model_dump(mode="json"),
                "val_score": {"parent": scores[0], "this": max(scores)},
                "partitions": {"feedback": "evo-train", "selection": "evo-val"},
            },
        )
        summary["saved"] = str(save_bundle(bundle, directory=args.bundle_dir))
    Path(args.run_dir, "evolution.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({k: v for k, v in summary.items() if k != "evaluations"}, indent=2))
    return 0


def _review(args, parser):
    from . import review

    worlds = [
        world
        for _, world in load_dataset(args.cases)
        if world["partition"] == args.partition
        and (not args.families or world["family"] in args.families.split(","))
    ][: args.limit]
    if args.fake:
        model, label = review.OracleReviewer(worlds), "oracle-fake"
    elif not args.key_file:
        parser.error("--key-file is required unless --fake is given")
    else:
        from shopsteward_agent.context import ModelProfile
        from shopsteward_agent.model import OpenAIModel

        label = args.model + (f"@{args.effort}" if args.effort else "")
        # Reasoning models spend output tokens before the answer; leave room for both.
        profile = ModelProfile(
            profile_id="review-" + label,
            model_id=args.model,
            max_input_tokens=128000,
            max_output_tokens=args.max_output_tokens,
            timeout_s=180,
            reasoning_effort=args.effort,
        )
        model = Retrying(
            OpenAIModel(
                base_url=args.base_url, model=args.model, key_file=args.key_file, profile=profile
            )
        )
    outcome = asyncio.run(
        review.run_batch(
            worlds,
            arms=args.arms.split(","),
            model=model,
            model_id=label,
            replicates=args.replicates,
            out=args.out,
            parallel=args.parallel,
            max_model_calls=args.max_model_calls,
        )
    )
    print(
        json.dumps(
            {
                "new_runs": len(outcome["records"]),
                "skipped_for_limit": len(outcome["skipped_for_limit"]),
                "errors_to_rerun": outcome["provider_errors"],
                "model_calls_planned": outcome["model_calls_planned"],
            }
        )
    )
    rows = review.summarize(review.load_records(args.out))
    Path(args.out, "review-summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    Path(args.out, "review-summary.md").write_text(
        review.markdown(rows), encoding="utf-8", newline="\n"
    )
    print(review.markdown(rows))
    return 0


def _source(args, parser):
    from shopsteward_agent.context import ModelProfile

    from . import endtoend

    worlds = [
        world
        for _, world in load_dataset(args.cases)
        if world["partition"] == args.partition
        and (not args.families or world["family"] in args.families.split(","))
    ][: args.limit]

    def profile(model_id):
        # Reasoning models spend output tokens before the answer; leave room for both.
        return ModelProfile(
            profile_id="source-" + model_id,
            model_id=model_id,
            api_mode=args.api_mode,
            max_input_tokens=128000,
            max_output_tokens=args.max_output_tokens,
            timeout_s=120,
            reasoning_effort=args.effort,
        )

    def client(model_id):
        from shopsteward_agent.model import OpenAIModel

        chosen = profile(model_id)
        return Retrying(
            OpenAIModel(
                base_url=args.base_url, model=model_id, key_file=args.key_file, profile=chosen
            )
        ), chosen

    if args.fake:
        model, chosen, roles, label = endtoend.OracleDesk(worlds), profile("oracle-fake"), {}, None
    elif not args.key_file:
        parser.error("--key-file is required unless --fake is given")
    else:
        model, chosen = client(args.model)
        named = {"supplier": args.reviewer_model, "supplier_escalation": args.second_model}
        roles = {role: client(model_id) for role, model_id in named.items() if model_id}
        label = (
            f"review={args.reviewer_model or args.model} "
            f"second={args.second_model or args.reviewer_model or args.model} "
            f"explain={args.model}"
        )
        # Text versions are part of the setup; the seed pair keeps the short label.
        if (args.bundle, args.review_bundle) != ("seed", "seed"):
            label += f" text={args.review_bundle}/{args.bundle}"
    from shopsteward_agent.cases import load_bundle

    outcome = asyncio.run(
        endtoend.run_batch(
            worlds,
            model=model,
            profile=chosen,
            role_models=roles,
            label=label,
            replicates=args.replicates,
            out=args.out,
            parallel=args.parallel,
            bundle=load_bundle(args.bundle),
            review_bundle=load_bundle(args.review_bundle, bundle_id="supplier-review"),
        )
    )
    print(
        json.dumps(
            {
                "new_runs": len(outcome["records"]),
                "provider_errors_to_rerun": outcome["provider_errors"],
            }
        )
    )
    rows = endtoend.summarize(endtoend.load_records(args.out))
    Path(args.out, "endtoend-summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    Path(args.out, "endtoend-summary.md").write_text(
        endtoend.markdown(rows), encoding="utf-8", newline="\n"
    )
    print(endtoend.markdown(rows))
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="shopsteward_pt.strategy_eval")
    commands = parser.add_subparsers(dest="command", required=True)
    generate = commands.add_parser("generate", help="write a deterministic dataset")
    generate.add_argument("--out", required=True)
    generate.add_argument(
        "--sourcing", action="store_true", help="supplier worlds built from <out>/sources.json"
    )
    sources = commands.add_parser("sources", help="slice the public raw data the worlds use")
    sources.add_argument("--m5-raw", required=True, help="folder with the three M5 csv files")
    sources.add_argument("--m5-series", required=True, help="the forecast series-manifest.json")
    sources.add_argument("--dataco", required=True, help="DataCoSupplyChainDataset.csv")
    sources.add_argument("--out", required=True)
    run = commands.add_parser("run", help="run a batch; finished runs in --out are skipped")
    run.add_argument("--cases", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--partition", required=True)
    run.add_argument("--limit", type=int)
    run.add_argument("--families")
    run.add_argument("--strategies", default="fixed,single,static_multi,adaptive_multi")
    run.add_argument("--bundle", default="seed")
    run.add_argument("--bundle-dir")
    run.add_argument("--replicates", type=int, default=1)
    run.add_argument("--parallel", type=int, default=2)
    run.add_argument("--max-model-calls", type=int)
    run.add_argument("--model", default="deepseek-flash")
    run.add_argument("--base-url", default="https://api.deepseek.com")
    run.add_argument("--key-file")
    run.add_argument("--fake", action="store_true", help="offline oracle model, no network")
    report = commands.add_parser("report", help="summarize the runs recorded in --out")
    report.add_argument("--out", required=True)
    evolve = commands.add_parser("evolve", help="GEPA search; optimizer environment only")
    evolve.add_argument("--cases", required=True)
    evolve.add_argument("--run-dir", required=True)
    evolve.add_argument("--revision", required=True)
    evolve.add_argument("--strategy", required=True)
    evolve.add_argument(
        "--components", default="question.evidence,question.impact,question.options"
    )
    evolve.add_argument("--max-metric-calls", type=int, required=True)
    evolve.add_argument("--minibatch", type=int, default=3)
    evolve.add_argument("--seed", type=int, default=0)
    evolve.add_argument("--parallel", type=int, default=3)
    evolve.add_argument("--bundle", default="seed")
    evolve.add_argument("--bundle-dir")
    evolve.add_argument("--model", default="deepseek-flash")
    evolve.add_argument("--reflection-model", default="deepseek-v4-pro")
    evolve.add_argument("--base-url", default="https://api.deepseek.com")
    evolve.add_argument("--key-file", required=True)
    review = commands.add_parser(
        "review", help="supplier reviews over sourcing worlds; prints the summary of --out"
    )
    review.add_argument("--cases", required=True)
    review.add_argument("--out", required=True)
    review.add_argument("--partition", required=True)
    review.add_argument("--limit", type=int)
    review.add_argument("--families")
    review.add_argument("--arms", default="split,joint")
    review.add_argument("--replicates", type=int, default=1)
    review.add_argument("--parallel", type=int, default=4)
    review.add_argument("--max-model-calls", type=int)
    review.add_argument("--model", default="deepseek-flash")
    review.add_argument("--base-url", default="https://api.deepseek.com")
    review.add_argument("--key-file")
    review.add_argument("--effort", help="reasoning effort, for models that take one")
    review.add_argument("--max-output-tokens", type=int, default=16000)
    review.add_argument("--fake", action="store_true", help="offline true cards, no network")
    source = commands.add_parser(
        "source", help="the whole sourcing loop in the agent runtime; prints the summary of --out"
    )
    source.add_argument("--cases", required=True)
    source.add_argument("--out", required=True)
    source.add_argument("--partition", required=True)
    source.add_argument("--limit", type=int)
    source.add_argument("--families")
    source.add_argument("--replicates", type=int, default=1)
    source.add_argument("--parallel", type=int, default=2, help="worlds in flight")
    source.add_argument("--model", default="gpt-6-luna", help="explains; reviews unless overridden")
    source.add_argument("--reviewer-model", help="first reading of each supplier")
    source.add_argument("--second-model", help="second reading of a rejected card")
    source.add_argument("--bundle", default="seed", help="text version of the explanation")
    source.add_argument("--review-bundle", default="seed", help="text version of the reviewers")
    source.add_argument("--base-url", default="https://api.openai.com/v1")
    # Some models only accept tools together with reasoning on the Responses API.
    source.add_argument(
        "--api-mode", default="responses", choices=["responses", "chat_completions"]
    )
    source.add_argument("--key-file")
    source.add_argument("--effort", help="reasoning effort, for models that take one")
    source.add_argument("--max-output-tokens", type=int, default=16000)
    source.add_argument("--fake", action="store_true", help="offline true answers, no network")
    gate = commands.add_parser("gate", help="paired release check of a candidate text version")
    gate.add_argument("--out", required=True)
    gate.add_argument("--strategy", required=True)
    gate.add_argument("--baseline", default="seed")
    gate.add_argument("--candidate", required=True)
    args = parser.parse_args(argv)

    if args.command == "generate":
        if args.sourcing:
            from .sourcing import write_dataset as write_worlds

            manifest = write_worlds(args.out)
        else:
            manifest = write_dataset(args.out)
        print(json.dumps({k: len(v) for k, v in manifest["partitions"].items()}))
        return 0
    if args.command == "sources":
        from .sources import build

        built = build(
            m5_raw=args.m5_raw, m5_series=args.m5_series, dataco=args.dataco, out=args.out
        )
        print(json.dumps({"m5_weeks": len(built["m5"]["windows"]), **built["dataco"]["modes"]}))
        return 0
    if args.command == "run":
        from shopsteward_agent.cases import load_bundle

        pairs = [
            (case, fixture)
            for case, fixture in load_dataset(args.cases)
            if fixture["partition"] == args.partition
            and (not args.families or fixture["family"] in args.families.split(","))
        ][: args.limit]
        if not args.fake and not args.key_file:
            parser.error("--key-file is required unless --fake is given")
        model, profile = _model(args, [fixture for _, fixture in pairs])
        outcome = asyncio.run(
            run_batch(
                pairs,
                strategies=args.strategies.split(","),
                bundle=load_bundle(args.bundle, directory=args.bundle_dir),
                model=model,
                profile=profile,
                replicates=args.replicates,
                out=args.out,
                parallel=args.parallel,
                max_model_calls=args.max_model_calls,
            )
        )
        print(
            json.dumps(
                {
                    "new_runs": len(outcome["records"]),
                    "skipped_for_limit": len(outcome["skipped_for_limit"]),
                    "provider_errors_to_rerun": len(outcome["provider_errors"]),
                    "model_calls_sent": outcome["model_calls_sent"],
                }
            )
        )
    if args.command == "evolve":
        return _evolve(args)
    if args.command == "review":
        return _review(args, parser)
    if args.command == "source":
        return _source(args, parser)
    if args.command == "gate":
        verdict = gate_report(
            load_records(args.out),
            strategy=args.strategy,
            baseline=args.baseline,
            candidate=args.candidate,
        )
        Path(args.out, f"gate-{args.candidate}-{args.strategy}.json").write_text(
            json.dumps(verdict, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        print(json.dumps(verdict, ensure_ascii=False, indent=2))
        return 0
    rows = summarize(load_records(args.out))
    Path(args.out, "summary.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    Path(args.out, "summary.md").write_text(markdown(rows), encoding="utf-8", newline="\n")
    print(markdown(rows))
    return 0
