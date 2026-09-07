export interface paths {
    "/api/v1/alerts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Listing */
        get: operations["list_alerts"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/alerts/{alert_id}/acknowledgement": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Acknowledge */
        post: operations["acknowledge_alert"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/conversations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Conversations */
        get: operations["list_agent_conversations"];
        put?: never;
        /** Create */
        post: operations["create_agent_conversation"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Messages */
        get: operations["list_agent_messages"];
        put?: never;
        /** Send */
        post: operations["send_agent_message"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-runs/{run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Detail */
        get: operations["get_agent_run"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-runs/{run_id}/resume": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Resume */
        post: operations["resume_agent_run"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/agent-runs/{run_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Cancel */
        post: operations["cancel_agent_run"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/conversations/{conversation_id}/followup": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Followup */
        patch: operations["configure_agent_followup"];
        trace?: never;
    };
    "/api/v1/stores/{store_id}/agent-knowledge": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Knowledge Read */
        get: operations["list_agent_knowledge"];
        put?: never;
        /** Knowledge Write */
        post: operations["edit_agent_knowledge"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/agent-tools/{tool_name}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Call */
        post: operations["call_agent_tool"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/dashboard": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Dashboard */
        get: operations["get_dashboard"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/timeline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Timeline */
        get: operations["list_mission_timeline"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Sales */
        get: operations["list_sales"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/sales/summary": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Sales Summary */
        get: operations["get_sales_summary"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/actions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Actions */
        get: operations["list_actions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/inbounds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Inbounds */
        get: operations["list_inbounds"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/ledger-entries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ledger Entries */
        get: operations["list_ledger_entries"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/plans/{plan_id}/decision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Decision */
        post: operations["decide_plan"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/actions/{action_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Action */
        get: operations["get_action"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/plans/{plan_id}/revision": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Revise */
        post: operations["revise_plan"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Current User */
        get: operations["get_current_user"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/stores": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Stores */
        get: operations["list_visible_stores"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Live */
        get: operations["health_live"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Ready */
        get: operations["health_ready"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/monitoring/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Monitoring */
        get: operations["get_monitoring_status"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/job-runs/{job_run_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Job */
        get: operations["get_job_run"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/catalog": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Catalog */
        get: operations["get_catalog"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/events/batches": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Events */
        post: operations["ingest_event_batch"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Listing */
        get: operations["list_missions"];
        put?: never;
        /** Create */
        post: operations["create_mission"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Detail */
        get: operations["get_mission"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/control": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Control */
        post: operations["control_mission"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/schedule": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Update Schedule */
        patch: operations["update_mission_schedule"];
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/checks": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Check */
        post: operations["request_mission_check"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/missions/{mission_id}/plans": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Plans */
        get: operations["list_mission_plans"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/plans/{plan_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Plan */
        get: operations["get_plan"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/stores/{store_id}/documents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Listing
         * @description Metadata filters only; q matches literal title substrings. Full-text search is K2.
         */
        get: operations["list_knowledge_documents"];
        put?: never;
        /**
         * Create
         * @description Upload original + UploadMetadata JSON. Returns UPLOADED/NOT_INDEXED; indexing is K2.
         */
        post: operations["create_knowledge_document"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Detail */
        get: operations["get_knowledge_document"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /** Patch */
        patch: operations["patch_knowledge_document"];
        trace?: never;
    };
    "/api/v1/documents/{document_id}/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Versions */
        get: operations["list_knowledge_versions"];
        put?: never;
        /**
         * Append
         * @description Upload original + AppendMetadata JSON (expected_metadata_version and validity).
         */
        post: operations["append_knowledge_version"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/versions/{version_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Version */
        get: operations["get_knowledge_version"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/versions/{version_id}/content": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Content
         * @description Authenticated attachment only. Parsed representations and activation are K2.
         */
        get: operations["download_knowledge_original"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/documents/{document_id}/control": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Control */
        post: operations["control_knowledge_document"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/dev/v1/scenarios": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Create Scenario */
        post: operations["create_dev_scenario"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/dev/v1/scenarios/{run_id}/advance": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Advance Scenario */
        post: operations["advance_dev_scenario"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /** Action */
        Action: {
            /** Id */
            id: string;
            /** Mission Id */
            mission_id: string;
            /** Plan Id */
            plan_id: string;
            /** Approval Id */
            approval_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "QUEUED" | "EXECUTING" | "SUCCEEDED" | "FAILED" | "UNKNOWN" | "STALE" | "CANCELLED";
            /** Quantity */
            quantity: number;
            /** Amount Minor */
            amount_minor: number;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /** External Order Id */
            external_order_id: string | null;
            receipt: components["schemas"]["PurchaseReceipt"] | null;
            /** Last Error */
            last_error: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            purchase_snapshot: components["schemas"]["ProposedPurchase"];
        };
        /** ActionList */
        ActionList: {
            context: components["schemas"]["ReadContext"];
            /** Items */
            items: components["schemas"]["Action"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** Alert */
        Alert: {
            /** Id */
            id: string;
            /** Store Id */
            store_id: string;
            /** Mission Id */
            mission_id: string | null;
            /** Sku Id */
            sku_id: string | null;
            /**
             * Type
             * @enum {string}
             */
            type: "STOCKOUT_RISK" | "CASH_CONSTRAINT" | "ACTION_EXCEPTION" | "DATA_STALE";
            /**
             * Severity
             * @enum {string}
             */
            severity: "INFO" | "WARNING" | "CRITICAL";
            /**
             * Status
             * @enum {string}
             */
            status: "OPEN" | "ACKNOWLEDGED" | "RESOLVED";
            /** Summary */
            summary: string;
            facts: components["schemas"]["AlertFacts"];
            /** State Version */
            state_version: number | null;
            /** Related Plan Id */
            related_plan_id: string | null;
            /**
             * First Seen At
             * Format: date-time
             */
            first_seen_at: string;
            /**
             * Last Seen At
             * Format: date-time
             */
            last_seen_at: string;
            /** Resolved At */
            resolved_at: string | null;
        };
        /** AlertFacts */
        AlertFacts: {
            /** Shortage Qty */
            shortage_qty?: number;
            /** Cash Floor Minor */
            cash_floor_minor?: number;
            /** Available Cash Minor */
            available_cash_minor?: number;
            /** Action Id */
            action_id?: string;
            /**
             * Data As Of
             * Format: date-time
             */
            data_as_of?: string;
            /** Reason */
            reason?: string;
        };
        /** AlertList */
        AlertList: {
            /** Items */
            items: components["schemas"]["Alert"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** Candidate */
        Candidate: {
            /** Id */
            id: string;
            /** Quantity */
            quantity: number;
            /** Spend Minor */
            spend_minor: number;
            /** Cash After Minor */
            cash_after_minor: number;
            /** Shortage Qty */
            shortage_qty: number;
            /** Feasible */
            feasible: boolean;
            /** Rejection Reasons */
            rejection_reasons: string[];
        };
        /** Catalog */
        Catalog: {
            /** Store Id */
            store_id: string;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /** Products */
            products: components["schemas"]["Product"][];
            /** Offers */
            offers: components["schemas"]["Offer"][];
        };
        /** CheckRequest */
        CheckRequest: {
            /**
             * Reason
             * @default
             */
            reason: string;
        };
        /** Control */
        Control: {
            /**
             * Operation
             * @enum {string}
             */
            operation: "archive" | "restore";
            /** Expected Metadata Version */
            expected_metadata_version: number;
        };
        /** ConversationCreate */
        ConversationCreate: {
            /**
             * Title
             * @default 经营对话
             */
            title: string;
            /**
             * Is Default
             * @default false
             */
            is_default: boolean;
        };
        /** ConversationList */
        ConversationList: {
            /** Items */
            items: components["schemas"]["ConversationView"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** ConversationView */
        ConversationView: {
            /** Id */
            id: string;
            /** Principal Id */
            principal_id: string;
            /** Mission Id */
            mission_id: string;
            /** Store Id */
            store_id: string;
            /** Title */
            title: string;
            /** Is Default */
            is_default: boolean;
            /** Active Run Id */
            active_run_id: string | null;
            /** Followup Enabled */
            followup_enabled: boolean;
            /** Followup Interval */
            followup_interval: number;
            /** Followup Version */
            followup_version: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** CurrentUser */
        CurrentUser: {
            /** Principal Id */
            principal_id: string;
            /** Roles */
            roles: ("viewer" | "operator" | "approver" | "admin")[];
            /**
             * Store Scope
             * @enum {string}
             */
            store_scope: "ALL" | "ASSIGNED";
        };
        /** Dashboard */
        Dashboard: {
            state: components["schemas"]["State"];
            freshness: components["schemas"]["Freshness"];
            /** Active Mission Count */
            active_mission_count: number;
            /** Active Alert Count */
            active_alert_count: number;
            /** Last Check At */
            last_check_at: string | null;
            /** Next Check At */
            next_check_at: string | null;
        };
        /** DecisionApproved */
        DecisionApproved: {
            /** Plan Id */
            plan_id: string;
            /**
             * Decision
             * @constant
             */
            decision: "approve";
            /** Action Id */
            action_id: string;
            /** Job Run Id */
            job_run_id: string;
        };
        /** DecisionRejected */
        DecisionRejected: {
            /** Plan Id */
            plan_id: string;
            /**
             * Decision
             * @constant
             */
            decision: "reject";
            /** Action Id */
            action_id: null;
            /** Job Run Id */
            job_run_id: null;
        };
        /** DecisionSnapshot */
        DecisionSnapshot: {
            /**
             * Snapshot Version
             * @constant
             */
            snapshot_version: "decision-v1";
            state: components["schemas"]["State"];
            /** Mission Version */
            mission_version: number;
            policy: components["schemas"]["Policy"];
            /** Task Constraints */
            task_constraints?: {
                [key: string]: number;
            };
            /** Policy Version */
            policy_version: string;
            forecast: components["schemas"]["ForecastSnapshot"];
            offer: components["schemas"]["Offer"];
            /** Inbound Items */
            inbound_items: components["schemas"]["InboundSnapshot"][];
            /** Eligible Inbound Qty */
            eligible_inbound_qty: number;
            /** Rule Version */
            rule_version: string;
            /**
             * Evaluated At
             * Format: date-time
             */
            evaluated_at: string;
            /**
             * Last Successful Sync At
             * Format: date-time
             */
            last_successful_sync_at: string;
            /**
             * Source Fresh Until
             * Format: date-time
             */
            source_fresh_until: string;
        };
        /** DemandEvent */
        DemandEvent: {
            /** Event Id */
            event_id: string;
            /** Sequence */
            sequence: number;
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1.0";
            /** Store Id */
            store_id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /**
             * Simulation Time
             * Format: date-time
             */
            simulation_time: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            event_type: "DEMAND_REVISED";
            payload: components["schemas"]["DemandPayload"];
        };
        /** DemandPayload */
        DemandPayload: {
            /** Sku Id */
            sku_id: string;
            /** Remaining Demand */
            remaining_demand: number;
            /** Forecast Version */
            forecast_version: string;
            /**
             * Data As Of
             * Format: date-time
             */
            data_as_of: string;
            /**
             * Valid Until
             * Format: date-time
             */
            valid_until: string;
            /**
             * Horizon Start
             * Format: date-time
             */
            horizon_start: string;
            /**
             * Horizon End
             * Format: date-time
             */
            horizon_end: string;
        };
        /** Document */
        Document: {
            /** Title */
            title: string;
            /**
             * Category
             * @default general
             */
            category: string;
            /** Sku Ids */
            sku_ids?: string[];
            /** Supplier Ids */
            supplier_ids?: string[];
            /**
             * Visibility
             * @default store
             * @enum {string}
             */
            visibility: "store" | "private";
            /** Id */
            id: string;
            /** Store Id */
            store_id: string;
            /** Owner Principal Id */
            owner_principal_id: string;
            /** Metadata Version */
            metadata_version: number;
            /**
             * Status
             * @enum {string}
             */
            status: "active" | "archived";
            /** Latest Version Id */
            latest_version_id: string | null;
            /**
             * Ingestion Status
             * @constant
             */
            ingestion_status: "UPLOADED";
            /**
             * Indexing Status
             * @constant
             */
            indexing_status: "NOT_INDEXED";
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** DocumentList */
        DocumentList: {
            /** Items */
            items: components["schemas"]["Document"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** Error */
        Error: {
            error: components["schemas"]["ErrorDetail"];
        };
        /** ErrorDetail */
        ErrorDetail: {
            /** Code */
            code: string;
            /** Message */
            message: string;
            /** Request Id */
            request_id: string;
            /** Retryable */
            retryable: boolean;
            /** Details */
            details: {
                [key: string]: unknown;
            };
        };
        /** EventBatch */
        EventBatch: {
            /**
             * Source
             * @constant
             */
            source: "simulation";
            /** Scenario Run Id */
            scenario_run_id: string;
            /** Events */
            events: (components["schemas"]["SaleEvent"] | components["schemas"]["DemandEvent"] | components["schemas"]["ReceivedEvent"] | components["schemas"]["PurchaseEvent"])[];
        };
        /** EventBatchResult */
        EventBatchResult: {
            /** Accepted Event Ids */
            accepted_event_ids: string[];
            /** Duplicate Event Ids */
            duplicate_event_ids: string[];
            /** Last Sequence */
            last_sequence: number;
        };
        /** Followup */
        Followup: {
            /** Enabled */
            enabled: boolean;
            /**
             * Interval Seconds
             * @default 300
             */
            interval_seconds: number;
            /** Expected Version */
            expected_version: number;
        };
        /** ForecastSnapshot */
        ForecastSnapshot: {
            /** Forecast Id */
            forecast_id: string;
            /** Forecast Version */
            forecast_version: string;
            /** Store Id */
            store_id: string;
            /** Sku Id */
            sku_id: string;
            /** Remaining Demand */
            remaining_demand: number;
            /**
             * Unit
             * @constant
             */
            unit: "piece";
            /**
             * Data As Of
             * Format: date-time
             */
            data_as_of: string;
            /** Source Sequence */
            source_sequence: number;
            /**
             * Horizon Start
             * Format: date-time
             */
            horizon_start: string;
            /**
             * Horizon End
             * Format: date-time
             */
            horizon_end: string;
            /**
             * Valid Until
             * Format: date-time
             */
            valid_until: string;
            /**
             * Source
             * @enum {string}
             */
            source: "fixed" | "manual" | "model";
            /** Model Name */
            model_name: string;
            /** Model Version */
            model_version: string;
            /** Assumptions */
            assumptions: string[];
        };
        /** Freshness */
        Freshness: {
            /**
             * Status
             * @enum {string}
             */
            status: "FRESH" | "STALE" | "UNKNOWN";
            /** Data As Of */
            data_as_of: string | null;
            /** Last Sync At */
            last_sync_at: string | null;
        };
        /** Health */
        Health: {
            /**
             * Status
             * @enum {string}
             */
            status: "ok" | "unavailable";
            /** Component */
            component: string;
        };
        /** InboundItem */
        InboundItem: {
            /** Action Id */
            action_id: string;
            /** Mission Id */
            mission_id: string;
            /** Sku Id */
            sku_id: string;
            /** External Order Id */
            external_order_id: string | null;
            /** Ordered Quantity */
            ordered_quantity: number;
            /** Received Quantity */
            received_quantity: number;
            /** Remaining Quantity */
            remaining_quantity: number;
            /** Expected Arrival At */
            expected_arrival_at: string | null;
            /**
             * Arrival Status
             * @enum {string}
             */
            arrival_status: "NOT_RECEIVED" | "PARTIALLY_RECEIVED" | "RECEIVED";
            /** Is Overdue */
            is_overdue: boolean | null;
        };
        /** InboundList */
        InboundList: {
            context: components["schemas"]["ReadContext"];
            /** Items */
            items: components["schemas"]["InboundItem"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** InboundSnapshot */
        InboundSnapshot: {
            /** Action Id */
            action_id: string;
            /** Sku Id */
            sku_id: string;
            /** Remaining Quantity */
            remaining_quantity: number;
            /** Expected Arrival At */
            expected_arrival_at: string | null;
            /** Eligible */
            eligible: boolean;
        };
        /** JobAccepted */
        JobAccepted: {
            /** Job Run Id */
            job_run_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "READY" | "RUNNING" | "RETRY_WAIT";
            /** Merged */
            merged: boolean;
        };
        /** JobResult */
        JobResult: {
            /** Summary */
            summary: string;
            /** References */
            references: components["schemas"]["Reference"][];
            /**
             * Check Status
             * @enum {string}
             */
            check_status?: "HEALTHY" | "ANOMALY" | "INCONCLUSIVE" | "SKIPPED";
            /** Input State Version */
            input_state_version?: number;
            /** Output State Version */
            output_state_version?: number;
        };
        /** JobRun */
        JobRun: {
            /** Id */
            id: string;
            /** Mission Id */
            mission_id: string | null;
            /**
             * Job Type
             * @enum {string}
             */
            job_type: "worker_probe" | "sync_events" | "check_mission" | "execute_purchase" | "reconcile_action" | "check_freshness" | "agent_followup" | "initialize_scenario" | "advance_scenario";
            /**
             * Trigger Source
             * @enum {string}
             */
            trigger_source: "INTERVAL" | "AT" | "EVENT" | "MANUAL" | "APPROVAL";
            /**
             * Status
             * @enum {string}
             */
            status: "READY" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED" | "RETRY_WAIT";
            /** Attempt Count */
            attempt_count: number;
            /**
             * Scheduled For
             * Format: date-time
             */
            scheduled_for: string;
            /**
             * Available At
             * Format: date-time
             */
            available_at: string;
            /** Started At */
            started_at: string | null;
            /** Finished At */
            finished_at: string | null;
            result: components["schemas"]["JobResult"] | null;
            /** Error Code */
            error_code: string | null;
            /** Last Error */
            last_error: string | null;
            /** Request Id */
            request_id: string | null;
        };
        /** KnowledgeChange */
        KnowledgeChange: {
            /**
             * Kind
             * @default USER
             * @enum {string}
             */
            kind: "USER" | "NOTES" | "SKILL";
            /**
             * Task Type
             * @default
             */
            task_type: string;
            /** Expected Version */
            expected_version: number;
            /**
             * Operation
             * @description 新增偏好或scope为空时必须add；replace仅替换已存在entry_id；remove仅删除已存在entry_id。读取偏好不调用此工具。
             * @enum {string}
             */
            operation: "add" | "replace" | "remove";
            /**
             * Entry Id
             * @description replace/remove必须来自当前knowledge.entries[].id；add省略。不是scope_id或用户消息ID。
             */
            entry_id?: string | null;
            /**
             * Content
             * @default
             */
            content: string;
            /** Source Message Id */
            source_message_id?: string | null;
            /** Required Tools */
            required_tools?: string[];
        };
        /** KnowledgeList */
        KnowledgeList: {
            /** Items */
            items: components["schemas"]["KnowledgeView"][];
        };
        /** KnowledgeView */
        KnowledgeView: {
            /** Id */
            id: string;
            /**
             * Kind
             * @enum {string}
             */
            kind: "USER" | "NOTES" | "SKILL";
            /** Task Type */
            task_type: string;
            /** Version */
            version: number;
            /** Entries */
            entries: {
                [key: string]: unknown;
            }[];
        };
        /** LedgerChanges */
        LedgerChanges: {
            /** Cash Delta Minor */
            cash_delta_minor: number;
            /** Receivables Delta Minor */
            receivables_delta_minor: number;
            /** On Hand Delta */
            on_hand_delta: number;
            /** In Transit Delta */
            in_transit_delta: number;
        };
        /** LedgerEntryList */
        LedgerEntryList: {
            context: components["schemas"]["ReadContext"];
            /** Items */
            items: components["schemas"]["LedgerEntryView"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** LedgerEntryView */
        LedgerEntryView: {
            /** Id */
            id: string;
            /** State Version */
            state_version: number;
            /**
             * Effect Type
             * @enum {string}
             */
            effect_type: "INIT" | "PURCHASE_ACCEPTED" | "GOODS_RECEIVED" | "SALE_RECORDED" | "DEMAND_REVISED";
            /** Sku Id */
            sku_id: string | null;
            /** Action Id */
            action_id: string | null;
            /** Source Event Id */
            source_event_id: string | null;
            /** Occurred At */
            occurred_at: string | null;
            /** Simulation Time */
            simulation_time: string | null;
            changes: components["schemas"]["LedgerChanges"] | null;
            opening_state: components["schemas"]["State"] | null;
            /** Remaining Demand After */
            remaining_demand_after: number | null;
        };
        /** MessageAccepted */
        MessageAccepted: {
            /** Message Id */
            message_id: string;
            /** Agent Run Id */
            agent_run_id: string;
            /** Conversation Id */
            conversation_id: string;
        };
        /** MessageCreate */
        MessageCreate: {
            /** Content */
            content: string;
        };
        /** MessageList */
        MessageList: {
            /** Items */
            items: components["schemas"]["MessageView"][];
            /** Next After Seq */
            next_after_seq: number | null;
        };
        /** MessageView */
        MessageView: {
            /** Id */
            id: string;
            /** Conversation Id */
            conversation_id: string;
            /** Seq */
            seq: number;
            /**
             * Role
             * @enum {string}
             */
            role: "user" | "assistant";
            /** Content */
            content: string;
            /** Run Id */
            run_id: string | null;
            /** References */
            references: {
                [key: string]: unknown;
            }[];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** MetadataPatch */
        MetadataPatch: {
            /** Expected Metadata Version */
            expected_metadata_version: number;
            /** Title */
            title?: string | null;
            /** Category */
            category?: string | null;
            /** Sku Ids */
            sku_ids?: string[] | null;
            /** Supplier Ids */
            supplier_ids?: string[] | null;
            /** Visibility */
            visibility?: ("store" | "private") | null;
        };
        /** Mission */
        Mission: {
            /** Id */
            id: string;
            /** Store Id */
            store_id: string;
            /** Sku Id */
            sku_id: string;
            /** Objective */
            objective: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ACTIVE" | "PAUSED" | "COMPLETED" | "CANCELLED";
            /** Mission Version */
            mission_version: number;
            policy: components["schemas"]["Policy"];
            /** Policy Version */
            policy_version: string;
            schedule: components["schemas"]["Schedule"];
            /** Current Plan Id */
            current_plan_id: string | null;
            /** Current Action Id */
            current_action_id: string | null;
            /** Completion Criteria */
            completion_criteria: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** MissionControl */
        MissionControl: {
            /**
             * Operation
             * @enum {string}
             */
            operation: "pause" | "resume" | "complete" | "cancel";
            /** Expected Mission Version */
            expected_mission_version: number;
        };
        /** MissionCreate */
        MissionCreate: {
            /** Store Id */
            store_id: string;
            /** Sku Id */
            sku_id: string;
            /** Objective */
            objective: string;
            policy: components["schemas"]["Policy"];
            /** Check Interval Seconds */
            check_interval_seconds: number;
        };
        /** MissionList */
        MissionList: {
            /** Items */
            items: components["schemas"]["Mission"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** MonitoringStatus */
        MonitoringStatus: {
            /**
             * Worker Status
             * @enum {string}
             */
            worker_status: "RUNNING" | "STALE" | "STOPPED" | "UNKNOWN";
            /** Worker Heartbeat At */
            worker_heartbeat_at: string | null;
            /** Due Job Count */
            due_job_count: number;
            /** Oldest Due Seconds */
            oldest_due_seconds: number;
            /** Sources */
            sources: components["schemas"]["SourceStatus"][];
            /** Agent Enabled */
            agent_enabled: boolean;
            /**
             * Forecast Provider
             * @enum {string}
             */
            forecast_provider: "fixed" | "http";
        };
        /** Offer */
        Offer: {
            /** Supplier Id */
            supplier_id: string;
            /** Sku Id */
            sku_id: string;
            /** Unit Price Minor */
            unit_price_minor: number;
            /** Minimum Order Quantity */
            minimum_order_quantity: number;
            /** Pack Size */
            pack_size: number;
            /** Offer Version */
            offer_version: string;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /** Lead Time Seconds */
            lead_time_seconds: number;
            /**
             * Valid From
             * Format: date-time
             */
            valid_from: string;
            /**
             * Valid Until
             * Format: date-time
             */
            valid_until: string;
        };
        /** Plan */
        Plan: {
            /** Id */
            id: string;
            /** Mission Id */
            mission_id: string;
            /** Plan Version */
            plan_version: number;
            /** State Version */
            state_version: number;
            /** Forecast Version */
            forecast_version: string;
            /** Policy Version */
            policy_version: string;
            /** Rule Version */
            rule_version: string;
            /**
             * Status
             * @enum {string}
             */
            status: "PENDING_APPROVAL" | "APPROVED" | "REJECTED" | "SUPERSEDED" | "EXPIRED";
            input_snapshot: components["schemas"]["DecisionSnapshot"];
            /** Candidates */
            candidates: components["schemas"]["Candidate"][];
            /** Recommended Candidate Id */
            recommended_candidate_id: string | null;
            /** Proposal Hash */
            proposal_hash: string;
            /** Explanation */
            explanation: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            proposed_purchase: components["schemas"]["ProposedPurchase"] | null;
        };
        /** PlanDecision */
        PlanDecision: {
            /**
             * Decision
             * @enum {string}
             */
            decision: "approve" | "reject";
            /** Expected Plan Version */
            expected_plan_version: number;
            /** Expected State Version */
            expected_state_version: number;
            /** Proposal Hash */
            proposal_hash: string;
        };
        /** PlanList */
        PlanList: {
            /** Items */
            items: components["schemas"]["Plan"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** PlanRevisionRequest */
        PlanRevisionRequest: {
            /** Expected Mission Version */
            expected_mission_version: number;
            /** Max Purchase Qty */
            max_purchase_qty: number | null;
        };
        /** Policy */
        Policy: {
            /** Cash Floor Minor */
            cash_floor_minor: number;
            /** Candidate Quantities */
            candidate_quantities: number[];
            /** Supplier Id */
            supplier_id: string;
        };
        /** Product */
        Product: {
            /** Sku Id */
            sku_id: string;
            /** Name */
            name: string;
            /**
             * Unit
             * @constant
             */
            unit: "piece";
        };
        /** ProposedPurchase */
        ProposedPurchase: {
            /** Store Id */
            store_id: string;
            /** Sku Id */
            sku_id: string;
            /** Supplier Id */
            supplier_id: string;
            /** Quantity */
            quantity: number;
            /** Unit Price Minor */
            unit_price_minor: number;
            /** Total Minor */
            total_minor: number;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /**
             * Expected Arrival At
             * Format: date-time
             */
            expected_arrival_at: string;
        };
        /** PurchaseEvent */
        PurchaseEvent: {
            /** Event Id */
            event_id: string;
            /** Sequence */
            sequence: number;
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1.0";
            /** Store Id */
            store_id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /**
             * Simulation Time
             * Format: date-time
             */
            simulation_time: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            event_type: "PURCHASE_ACCEPTED";
            payload: components["schemas"]["PurchasePayload"];
        };
        /** PurchasePayload */
        PurchasePayload: {
            /** Action Id */
            action_id: string;
            /** Sku Id */
            sku_id: string;
            /** Quantity */
            quantity: number;
            /** External Order Id */
            external_order_id: string;
            /** Total Minor */
            total_minor: number;
        };
        /** PurchaseReceipt */
        PurchaseReceipt: {
            /** Action Id */
            action_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "ACCEPTED" | "REJECTED" | "PENDING";
            /** External Order Id */
            external_order_id: string | null;
            /** Quantity */
            quantity: number;
            /** Total Minor */
            total_minor: number;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /**
             * Recorded At
             * Format: date-time
             */
            recorded_at: string;
            /** Reason */
            reason: string | null;
        };
        /** ReadContext */
        ReadContext: {
            /** Store Id */
            store_id: string;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /** State Version */
            state_version: number;
            /**
             * As Of
             * Format: date-time
             */
            as_of: string;
            /** Simulation Time */
            simulation_time: string | null;
            /** Source Sequence */
            source_sequence: number | null;
            freshness: components["schemas"]["Freshness"];
        };
        /** ReceivedEvent */
        ReceivedEvent: {
            /** Event Id */
            event_id: string;
            /** Sequence */
            sequence: number;
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1.0";
            /** Store Id */
            store_id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /**
             * Simulation Time
             * Format: date-time
             */
            simulation_time: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            event_type: "GOODS_RECEIVED";
            payload: components["schemas"]["ReceivedPayload"];
        };
        /** ReceivedPayload */
        ReceivedPayload: {
            /** Action Id */
            action_id: string;
            /** Sku Id */
            sku_id: string;
            /** Quantity */
            quantity: number;
        };
        /** Reference */
        Reference: {
            /**
             * Type
             * @enum {string}
             */
            type: "mission" | "plan" | "action" | "event" | "forecast" | "artifact" | "scenario" | "store" | "alert";
            /** Id */
            id: string;
            /** Version */
            version?: string;
        };
        /** Resume */
        Resume: {
            /** Interrupt Id */
            interrupt_id: string;
            /** Content */
            content: string;
        };
        /** ResumeAccepted */
        ResumeAccepted: {
            /** Agent Run Id */
            agent_run_id: string;
            /** Message Id */
            message_id: string;
        };
        /** RunView */
        RunView: {
            /** Id */
            id: string;
            /** Conversation Id */
            conversation_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "QUEUED" | "RUNNING" | "WAITING_INPUT" | "SUCCEEDED" | "FAILED" | "CANCELLED";
            /** Input Through Seq */
            input_through_seq: number;
            /**
             * Trigger
             * @enum {string}
             */
            trigger: "USER" | "FOLLOWUP";
            /** Graph Version */
            graph_version: string;
            /** Interrupt Id */
            interrupt_id: string | null;
            /** Question */
            question: string | null;
            /** Output */
            output: {
                [key: string]: unknown;
            } | null;
            /** Error Code */
            error_code: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Finished At */
            finished_at: string | null;
            /** Tools */
            tools?: {
                [key: string]: unknown;
            }[];
        };
        /** SaleBucket */
        SaleBucket: {
            /**
             * From
             * Format: date-time
             */
            from: string;
            /**
             * To
             * Format: date-time
             */
            to: string;
            /** Record Count */
            record_count: number;
            /** Recorded Quantity */
            recorded_quantity: number;
            /** Recorded Sales Amount Minor */
            recorded_sales_amount_minor: number;
        };
        /** SaleEvent */
        SaleEvent: {
            /** Event Id */
            event_id: string;
            /** Sequence */
            sequence: number;
            /**
             * Schema Version
             * @constant
             */
            schema_version: "1.0";
            /** Store Id */
            store_id: string;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /**
             * Simulation Time
             * Format: date-time
             */
            simulation_time: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            event_type: "SALE_RECORDED";
            payload: components["schemas"]["SalePayload"];
        };
        /** SaleList */
        SaleList: {
            context: components["schemas"]["ReadContext"];
            /** Items */
            items: components["schemas"]["SaleRecord"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** SalePayload */
        SalePayload: {
            /** Sku Id */
            sku_id: string;
            /** Quantity */
            quantity: number;
            /** Unit Price Minor */
            unit_price_minor: number;
        };
        /** SaleRecord */
        SaleRecord: {
            /** Event Id */
            event_id: string;
            /** Sequence */
            sequence: number;
            /** Sku Id */
            sku_id: string;
            /** Quantity */
            quantity: number;
            /** Unit Price Minor */
            unit_price_minor: number;
            /** Sales Amount Minor */
            sales_amount_minor: number;
            /**
             * Occurred At
             * Format: date-time
             */
            occurred_at: string;
            /**
             * Simulation Time
             * Format: date-time
             */
            simulation_time: string;
        };
        /** SaleSummary */
        SaleSummary: {
            context: components["schemas"]["ReadContext"];
            /**
             * From
             * Format: date-time
             */
            from: string;
            /**
             * To
             * Format: date-time
             */
            to: string;
            /**
             * Time Basis
             * @constant
             */
            time_basis: "simulation_time";
            /**
             * Timezone
             * @constant
             */
            timezone: "UTC";
            /**
             * Granularity
             * @constant
             */
            granularity: "day";
            /**
             * Coverage
             * @constant
             */
            coverage: "RECORDED_EVENTS_ONLY";
            /** Record Count */
            record_count: number;
            /** Recorded Quantity */
            recorded_quantity: number;
            /** Recorded Sales Amount Minor */
            recorded_sales_amount_minor: number;
            /** Buckets */
            buckets: components["schemas"]["SaleBucket"][];
        };
        /** ScenarioAccepted */
        ScenarioAccepted: {
            /** Job Run Id */
            job_run_id: string;
            /**
             * Status
             * @enum {string}
             */
            status: "READY" | "RUNNING" | "RETRY_WAIT";
            /** Scenario Run Id */
            scenario_run_id: string | null;
            /** Store Id */
            store_id: string | null;
        };
        /** ScenarioAdvance */
        ScenarioAdvance: {
            /** Steps */
            steps: number;
        };
        /** ScenarioCreate */
        ScenarioCreate: {
            /**
             * Scenario
             * @enum {string}
             */
            scenario: "SC01" | "SANDBOX";
            /** Label */
            label?: string | null;
            parameters?: components["schemas"]["ScenarioParameters"] | null;
        };
        /** ScenarioParameters */
        ScenarioParameters: {
            /**
             * Cash Minor
             * @default 100000
             */
            cash_minor: number;
            /**
             * On Hand
             * @default 20
             */
            on_hand: number;
            /**
             * Remaining Demand
             * @default 60
             */
            remaining_demand: number;
            /**
             * Unit Price Minor
             * @default 1000
             */
            unit_price_minor: number;
            /**
             * Minimum Order Quantity
             * @default 20
             */
            minimum_order_quantity: number;
            /**
             * Pack Size
             * @default 20
             */
            pack_size: number;
            /**
             * Lead Time Seconds
             * @default 86400
             */
            lead_time_seconds: number;
            /**
             * Horizon Days
             * @default 7
             */
            horizon_days: number;
        };
        /** Schedule */
        Schedule: {
            /** Id */
            id: string;
            /**
             * Job Type
             * @constant
             */
            job_type: "check_mission";
            /** Mission Id */
            mission_id: string;
            /**
             * Trigger
             * @constant
             */
            trigger: "INTERVAL";
            /** Interval Seconds */
            interval_seconds: number;
            /** Enabled */
            enabled: boolean;
            /** Version */
            version: number;
            /** Next Run At */
            next_run_at: string | null;
        };
        /** ScheduleUpdate */
        ScheduleUpdate: {
            /** Interval Seconds */
            interval_seconds: number;
            /** Enabled */
            enabled: boolean;
            /** Expected Schedule Version */
            expected_schedule_version: number;
        };
        /** SourceStatus */
        SourceStatus: {
            /** Source */
            source: string;
            /** Last Success At */
            last_success_at: string | null;
            /** Last Sequence */
            last_sequence: number;
            /**
             * Status
             * @enum {string}
             */
            status: "FRESH" | "STALE" | "UNKNOWN";
            /** Last Error */
            last_error: string | null;
        };
        /** State */
        State: {
            /** Store Id */
            store_id: string;
            /** State Version */
            state_version: number;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /** Cash Minor */
            cash_minor: number;
            /** Reserved Cash Minor */
            reserved_cash_minor: number;
            /** Available Cash Minor */
            available_cash_minor: number;
            /** Receivables Minor */
            receivables_minor: number;
            /** Stocks */
            stocks: components["schemas"]["Stock"][];
            /** Data As Of */
            data_as_of: string | null;
            /** Simulation Time */
            simulation_time: string | null;
        };
        /** Stock */
        Stock: {
            /** Sku Id */
            sku_id: string;
            /** On Hand */
            on_hand: number;
            /** In Transit */
            in_transit: number;
            /** Remaining Demand */
            remaining_demand: number | null;
            /** Forecast Version */
            forecast_version: string | null;
        };
        /** StoreList */
        StoreList: {
            /** Items */
            items: components["schemas"]["StoreSummary"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** StoreSummary */
        StoreSummary: {
            /** Store Id */
            store_id: string;
            /**
             * Currency
             * @constant
             */
            currency: "CNY";
            /**
             * Source Type
             * @constant
             */
            source_type: "simulation";
            /** Simulation Time */
            simulation_time: string | null;
        };
        /** TimelineEntry */
        TimelineEntry: {
            /** Id */
            id: string;
            /** Mission Id */
            mission_id: string;
            /** Type */
            type: string;
            /** Summary */
            summary: string;
            /**
             * Actor Type
             * @enum {string}
             */
            actor_type: "USER" | "SERVICE" | "SYSTEM";
            /** Actor Id */
            actor_id: string | null;
            /** References */
            references: components["schemas"]["Reference"][];
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
        };
        /** TimelineEntryList */
        TimelineEntryList: {
            /** Items */
            items: components["schemas"]["TimelineEntry"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /** ToolCall */
        ToolCall: {
            /** Run Id */
            run_id: string;
            /** Invocation Id */
            invocation_id: string;
            /** Arguments */
            arguments?: {
                [key: string]: unknown;
            };
        };
        /** ToolResult */
        ToolResult: {
            /** Ok */
            ok: boolean;
            /** Data */
            data: {
                [key: string]: unknown;
            };
            /** References */
            references: {
                [key: string]: unknown;
            }[];
            /** Error */
            error?: {
                [key: string]: unknown;
            } | null;
        };
        /** Version */
        Version: {
            /** Valid From */
            valid_from?: string | null;
            /** Valid Until */
            valid_until?: string | null;
            /** Id */
            id: string;
            /** Document Id */
            document_id: string;
            /** Version No */
            version_no: number;
            /** Original Name */
            original_name: string;
            /** Mime Type */
            mime_type: string;
            /** Content Sha256 */
            content_sha256: string;
            /** Size Bytes */
            size_bytes: number;
            /** Created By */
            created_by: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Ingestion Status
             * @default UPLOADED
             * @constant
             */
            ingestion_status: "UPLOADED";
            /**
             * Indexing Status
             * @default NOT_INDEXED
             * @constant
             */
            indexing_status: "NOT_INDEXED";
        };
        /** VersionList */
        VersionList: {
            /** Items */
            items: components["schemas"]["Version"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_alerts: {
        parameters: {
            query: {
                store_id: string;
                mission_id?: string | null;
                status?: ("OPEN" | "ACKNOWLEDGED" | "RESOLVED") | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AlertList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    acknowledge_alert: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                alert_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Alert"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_agent_conversations: {
        parameters: {
            query?: {
                limit?: number;
                after?: string;
            };
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    create_agent_conversation: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConversationCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationView"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_agent_messages: {
        parameters: {
            query?: {
                limit?: number;
                after_seq?: number;
            };
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    send_agent_message: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageAccepted"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_agent_run: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunView"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    resume_agent_run: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Resume"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ResumeAccepted"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    cancel_agent_run: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RunView"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    configure_agent_followup: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                conversation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Followup"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConversationView"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_agent_knowledge: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                store_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    edit_agent_knowledge: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                store_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["KnowledgeChange"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["KnowledgeView"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    call_agent_tool: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                tool_name: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ToolCall"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ToolResult"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_dashboard: {
        parameters: {
            query: {
                store_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Dashboard"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_mission_timeline: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TimelineEntryList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_sales: {
        parameters: {
            query: {
                limit?: number;
                cursor?: string | null;
                store_id: string;
                sku_id?: string | null;
                from?: string | null;
                to?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SaleList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_sales_summary: {
        parameters: {
            query: {
                store_id: string;
                sku_id?: string | null;
                from: string;
                to: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SaleSummary"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_actions: {
        parameters: {
            query: {
                limit?: number;
                cursor?: string | null;
                store_id: string;
                mission_id?: string | null;
                sku_id?: string | null;
                status?: ("QUEUED" | "EXECUTING" | "SUCCEEDED" | "FAILED" | "UNKNOWN" | "STALE" | "CANCELLED") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ActionList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_inbounds: {
        parameters: {
            query: {
                limit?: number;
                cursor?: string | null;
                store_id: string;
                mission_id?: string | null;
                sku_id?: string | null;
                arrival_status?: ("NOT_RECEIVED" | "PARTIALLY_RECEIVED" | "RECEIVED") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["InboundList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_ledger_entries: {
        parameters: {
            query: {
                limit?: number;
                cursor?: string | null;
                store_id: string;
                effect_type?: ("INIT" | "PURCHASE_ACCEPTED" | "GOODS_RECEIVED" | "SALE_RECORDED" | "DEMAND_REVISED") | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LedgerEntryList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    decide_plan: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanDecision"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DecisionRejected"];
                };
            };
            /** @description Accepted */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DecisionApproved"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_action: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                action_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Action"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    revise_plan: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PlanRevisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Plan"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_current_user: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurrentUser"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_visible_stores: {
        parameters: {
            query?: {
                limit?: number;
                cursor?: string | null;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["StoreList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    health_live: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    health_ready: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Health"];
                };
            };
        };
    };
    get_monitoring_status: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MonitoringStatus"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_job_run: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                job_run_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobRun"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_catalog: {
        parameters: {
            query: {
                store_id: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Catalog"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    ingest_event_batch: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EventBatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EventBatchResult"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_missions: {
        parameters: {
            query: {
                store_id: string;
                status?: ("ACTIVE" | "PAUSED" | "COMPLETED" | "CANCELLED") | null;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MissionList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    create_mission: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MissionCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Mission"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_mission: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Mission"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    control_mission: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MissionControl"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Mission"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    update_mission_schedule: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScheduleUpdate"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Schedule"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    request_mission_check: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CheckRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobAccepted"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_mission_plans: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                mission_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PlanList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_plan: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                plan_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Plan"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_knowledge_documents: {
        parameters: {
            query?: {
                category?: string | null;
                supplier_id?: string | null;
                sku_id?: string | null;
                status?: "active" | "archived";
                q?: string;
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                store_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DocumentList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    create_knowledge_document: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                store_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": {
                    /** Format: binary */
                    file: string;
                    /** @description JSON-encoded UploadMetadata */
                    metadata: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Document"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_knowledge_document: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Document"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    patch_knowledge_document: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MetadataPatch"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Document"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    list_knowledge_versions: {
        parameters: {
            query?: {
                cursor?: string | null;
                limit?: number;
            };
            header?: never;
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["VersionList"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    append_knowledge_version: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": {
                    /** Format: binary */
                    file: string;
                    /** @description JSON-encoded AppendMetadata */
                    metadata: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Document"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    get_knowledge_version: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                document_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Version"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    download_knowledge_original: {
        parameters: {
            query?: {
                representation?: "original";
            };
            header?: never;
            path: {
                document_id: string;
                version_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/octet-stream": string;
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    control_knowledge_document: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                document_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["Control"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Document"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Request Entity Too Large */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    create_dev_scenario: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScenarioCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ScenarioAccepted"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
    advance_dev_scenario: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                run_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ScenarioAdvance"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JobAccepted"];
                };
            };
            /** @description Unauthorized */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Forbidden */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Not Found */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Conflict */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Unprocessable Entity */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Internal Server Error */
            500: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            /** @description Service Unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
        };
    };
}
