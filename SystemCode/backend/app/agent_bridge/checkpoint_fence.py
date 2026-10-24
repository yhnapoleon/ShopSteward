"""Lease ownership check on the exact connection that writes a graph checkpoint."""


def make_fence(job_id, lease_token):
    async def fence(conn):
        from shopsteward_agent import RuntimeFailure

        result = await conn.execute(
            "SELECT id FROM public.job_runs WHERE id=%s AND status='RUNNING' "
            "AND lease_token=%s AND lease_until>clock_timestamp() FOR UPDATE",
            (job_id, lease_token),
        )
        if await result.fetchone() is None:
            raise RuntimeFailure("lease_lost")

    return fence
