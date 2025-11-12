
resource "confluent_flink_statement" "flagged-user-materializer" {
    organization {
        id = data.terraform_remote_state.connector.outputs.organization_id
    }
    environment {
        id = data.terraform_remote_state.connector.outputs.environment_id
    }
    compute_pool {
        id = data.terraform_remote_state.connector.outputs.flink_compute_pool_id
    }
    principal {
        id = data.terraform_remote_state.connector.outputs.flink_principal_id
    }
    rest_endpoint = data.terraform_remote_state.connector.outputs.flink_rest_endpoint
    credentials {
        key    = data.terraform_remote_state.connector.outputs.flink_api_key
        secret = data.terraform_remote_state.connector.outputs.flink_api_secret
    }
    properties = {
        "sql.current-catalog"  = data.terraform_remote_state.connector.outputs.environment_name
        "sql.current-database" = data.terraform_remote_state.connector.outputs.kafka_cluster_name
        "client.statement-name" = "flagged-user-materializer"
    }
    statement = <<EOF
    CREATE TABLE flagged_user(
      ACCOUNT_ID DOUBLE, 
      user_name STRING,
      email STRING,
      total_amount DOUBLE,
      transaction_count BIGINT,
      updated_at TIMESTAMP_LTZ(3),
      PRIMARY KEY (ACCOUNT_ID) NOT ENFORCED
    )
    AS 
    WITH transactions_per_customer_10m AS (
      SELECT 
        ACCOUNT_ID,
        SUM(AMOUNT) OVER w AS total_amount,
        COUNT(*) OVER w AS transaction_count,
        `$rowtime`  AS transaction_time
      FROM user_transaction
      WINDOW w AS (
        PARTITION BY ACCOUNT_ID
        ORDER BY `$rowtime` 
        RANGE BETWEEN INTERVAL '10' MINUTE PRECEDING AND CURRENT ROW
      )
    ),
    flagged_user_rows AS (
      SELECT 
        t.ACCOUNT_ID,
        u.USERNAME AS user_name,
        u.EMAIL AS email,
        t.total_amount,
        t.transaction_count,
        t.transaction_time AS updated_at,
        ROW_NUMBER() OVER (PARTITION BY t.ACCOUNT_ID ORDER BY t.transaction_time DESC) AS rn
      FROM transactions_per_customer_10m t
      JOIN auth_user u 
        ON t.ACCOUNT_ID = u.ID
      WHERE t.total_amount > 1000 OR t.transaction_count > 10
    )
    SELECT 
      COALESCE(flagged_user_rows.ACCOUNT_ID, 0) AS ACCOUNT_ID, user_name, email, total_amount, transaction_count, updated_at
    FROM flagged_user_rows
    WHERE rn = 1;
    EOF
}