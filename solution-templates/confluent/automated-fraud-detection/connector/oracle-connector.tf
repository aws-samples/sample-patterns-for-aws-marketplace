resource "confluent_api_key" "oracle_xstream_api_key" {
    display_name = "oracle-xstream-api-key"
    description  = "API Key that is owned by 'env-manager' service account"
    owner {
        id          = confluent_service_account.app-manager.id
        api_version = confluent_service_account.app-manager.api_version
        kind        = confluent_service_account.app-manager.kind
    }
    managed_resource {
        id          = confluent_kafka_cluster.cluster.id
        api_version = confluent_kafka_cluster.cluster.api_version
        kind        = confluent_kafka_cluster.cluster.kind
        environment {
            id = confluent_environment.staging.id
        }
    }
    depends_on = [
        confluent_service_account.app-manager
    ]
}

resource "time_sleep" "wait_for_oracle" {
    depends_on = [
        data.terraform_remote_state.aws_resources
    ]
    create_duration = "2m"
}

resource "time_sleep" "wait_for_connector_data" {
    depends_on = [
        confluent_connector.oracle_xstream
    ]
    create_duration = "2m"
}

resource "confluent_connector" "oracle_xstream" {
    depends_on = [
        confluent_api_key.oracle_xstream_api_key,
        time_sleep.wait_for_oracle
    ]
    environment {
        id = confluent_environment.staging.id
    }
    kafka_cluster {
        id = confluent_kafka_cluster.cluster.id
    }
    config_nonsensitive = {
        "name" = "oracle-xstream"
        "connector.class" = "OracleXStreamSource"
        "database.dbname" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.database_name
        "database.hostname" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.database_hostname
        "database.port" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.database_port
        "database.user" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.database_username
        "database.password" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.database_password
        "database.service.name" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.database_service_name
        "database.out.server.name" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.xstream_outbound_server
        "database.pdb.name" = data.terraform_remote_state.aws_resources.outputs.oracle_xstream_connector.pluggable_database_name
        "table.inclusion.regex" = "SAMPLE[.](USER_TRANSACTION|AUTH_USER)"
        "topic.prefix" = "fd"
        "decimal.handling.mode" = "double"
        "database.processor.licenses" = "1"
        "output.data.format" = "JSON_SR"
        "output.key.format" = "JSON_SR"
        "tasks.max" = "1",
        "kafka.auth.mode" = "KAFKA_API_KEY",
        "kafka.api.key" = confluent_api_key.oracle_xstream_api_key.id,
        "kafka.api.secret" = confluent_api_key.oracle_xstream_api_key.secret,
        "csfle.enabled" = "false",
        "schema.context.name" = "default",
        "database.tls.mode" = "disable",
        "snapshot.mode" = "initial",
        "schema.history.internal.skip.unparseable.ddl" = "false",
        "snapshot.database.errors.max.retries" = "0",
        "tombstones.on.delete" = "true",
        "skipped.operations" = "t",
        "schema.name.adjustment.mode" = "none",
        "field.name.adjustment.mode" = "none",
        "heartbeat.interval.ms" = "0",
        "database.os.timezone" = "UTC",
        "unavailable.value.placeholder" = "__cflt_unavailable_value",
        "lob.oversize.threshold" = "-1",
        "lob.oversize.handling.mode" = "fail",
        "skip.value.placeholder" = "__cflt_skipped_value",
        "binary.handling.mode" = "bytes",
        "time.precision.mode" = "adaptive",
        "value.converter.decimal.format" = "BASE64",
        "value.converter.reference.subject.name.strategy" = "DefaultReferenceSubjectNameStrategy",
        "errors.tolerance" = "none",
        "value.converter.value.subject.name.strategy" = "TopicNameStrategy",
        "key.converter.key.subject.name.strategy" = "TopicNameStrategy",
        "auto.restart.on.user.error" = "true"
    }
}

resource "confluent_flink_statement" "switch-user-to-avro" {
    depends_on = [
        time_sleep.wait_for_connector_data
    ]
    organization {
        id = data.confluent_organization.main.id
    }
    environment {
        id = confluent_environment.staging.id
    }
    compute_pool {
        id = confluent_flink_compute_pool.flink_pool.id
    }
    principal {
        id = confluent_service_account.app-manager.id
    }
    rest_endpoint = data.confluent_flink_region.flink_region.rest_endpoint
    credentials {
        key    = confluent_api_key.flink-api-key.id
        secret = confluent_api_key.flink-api-key.secret
    }
    properties = {
        "sql.current-catalog"  = confluent_environment.staging.display_name
        "sql.current-database" = confluent_kafka_cluster.cluster.display_name
    }
    statement = <<EOF
    ALTER TABLE `fd.SAMPLE.AUTH_USER` SET ('changelog.mode' = 'append' , 'value.format' = 'avro-registry');
    EOF
}

resource "confluent_flink_statement" "create-user-table" {
    depends_on = [
        confluent_flink_statement.switch-user-to-avro
    ]
    organization {
        id = data.confluent_organization.main.id
    }
    environment {
        id = confluent_environment.staging.id
    }
    compute_pool {
        id = confluent_flink_compute_pool.flink_pool.id
    }
    principal {
        id = confluent_service_account.app-manager.id
    }
    rest_endpoint = data.confluent_flink_region.flink_region.rest_endpoint
    credentials {
        key    = confluent_api_key.flink-api-key.id
        secret = confluent_api_key.flink-api-key.secret
    }
    properties = {
        "sql.current-catalog"  = confluent_environment.staging.display_name
        "sql.current-database" = confluent_kafka_cluster.cluster.display_name
    }
    statement = <<EOF
    CREATE TABLE `auth_user` (
        `ID` DOUBLE,
        `PASSWORD` VARCHAR(2147483647),
        `LAST_LOGIN` BIGINT,
        `IS_SUPERUSER` DOUBLE,
        `USERNAME` VARCHAR(2147483647),
        `FIRST_NAME` VARCHAR(2147483647),
        `LAST_NAME` VARCHAR(2147483647),
        `EMAIL` VARCHAR(2147483647),
        `IS_STAFF` DOUBLE,
        `IS_ACTIVE` DOUBLE,
        `DATE_JOINED` BIGINT)
    DISTRIBUTED BY HASH(`ID`) INTO 1 BUCKETS
    WITH (
        'changelog.mode' = 'append',
        'connector' = 'confluent',
        'kafka.cleanup-policy' = 'delete',
        'kafka.max-message-size' = '8 mb',
        'kafka.retention.size' = '0 bytes',
        'kafka.retention.time' = '7 d',
        'key.format' = 'avro-registry',
        'scan.bounded.mode' = 'unbounded',
        'scan.startup.mode' = 'earliest-offset',
        'value.fields-include' = 'all',
        'value.format' = 'avro-registry'
    );
    EOF
}

resource "confluent_flink_statement" "insert-into-user-table" {
    depends_on = [
        confluent_flink_statement.create-user-table
    ]
    organization {
        id = data.confluent_organization.main.id
    }
    environment {
        id = confluent_environment.staging.id
    }
    compute_pool {
        id = confluent_flink_compute_pool.flink_pool.id
    }
    principal {
        id = confluent_service_account.app-manager.id
    }
    rest_endpoint = data.confluent_flink_region.flink_region.rest_endpoint
    credentials {
        key    = confluent_api_key.flink-api-key.id
        secret = confluent_api_key.flink-api-key.secret
    }
    properties = {
        "sql.current-catalog"  = confluent_environment.staging.display_name
        "sql.current-database" = confluent_kafka_cluster.cluster.display_name
    }
    statement = <<EOF
    INSERT INTO `auth_user`
    SELECT after.ID as ID,
        after.PASSWORD as PASSWORD,
        after.LAST_LOGIN as LAST_LOGIN,
        after.IS_SUPERUSER as IS_SUPERUSER,
        after.USERNAME as USERNAME,
        after.FIRST_NAME as FIRST_NAME,
        after.LAST_NAME as LAST_NAME,
        after.EMAIL as EMAIL,
        after.IS_STAFF as IS_STAFF,
        after.IS_ACTIVE as IS_ACTIVE,
        after.DATE_JOINED as DATE_JOINED
    FROM `fd.SAMPLE.AUTH_USER`;
    EOF
}

resource "confluent_flink_statement" "switch-transaction-to-avro" {
    depends_on = [ 
        time_sleep.wait_for_connector_data
    ]
    organization {
        id = data.confluent_organization.main.id
    }
    environment {
        id = confluent_environment.staging.id
    }
    compute_pool {
        id = confluent_flink_compute_pool.flink_pool.id
    }
    principal {
        id = confluent_service_account.app-manager.id
    }
    rest_endpoint = data.confluent_flink_region.flink_region.rest_endpoint
    credentials {
        key    = confluent_api_key.flink-api-key.id
        secret = confluent_api_key.flink-api-key.secret
    }
    properties = {
        "sql.current-catalog"  = confluent_environment.staging.display_name
        "sql.current-database" = confluent_kafka_cluster.cluster.display_name
    }
    statement = <<EOF
    ALTER TABLE `fd.SAMPLE.USER_TRANSACTION` SET ('changelog.mode' = 'append' , 'value.format' = 'avro-registry');
    EOF
}

resource "confluent_flink_statement" "create-user-transaction-table" {
    depends_on = [
        confluent_flink_statement.switch-transaction-to-avro
    ]
    organization {
        id = data.confluent_organization.main.id
    }
    environment {
        id = confluent_environment.staging.id
    }
    compute_pool {
        id = confluent_flink_compute_pool.flink_pool.id
    }
    principal {
        id = confluent_service_account.app-manager.id
    }
    rest_endpoint = data.confluent_flink_region.flink_region.rest_endpoint
    credentials {
        key    = confluent_api_key.flink-api-key.id
        secret = confluent_api_key.flink-api-key.secret
    }
    properties = {
        "sql.current-catalog"  = confluent_environment.staging.display_name
        "sql.current-database" = confluent_kafka_cluster.cluster.display_name
    }
    statement = <<EOF
    CREATE TABLE `user_transaction` (
        `ID` DOUBLE, 
        `AMOUNT` DOUBLE, 
        `RECEIVED_AT` BIGINT, 
        `IP_ADDRESS` VARCHAR(2147483647), 
        `ACCOUNT_ID` DOUBLE
    )
    DISTRIBUTED BY HASH(`ID`) INTO 1 BUCKETS
    WITH (
        'changelog.mode' = 'append',
        'connector' = 'confluent',
        'kafka.cleanup-policy' = 'delete',  
        'kafka.max-message-size' = '8 mb',
        'kafka.retention.size' = '0 bytes',
        'kafka.retention.time' = '7 d',
        'key.format' = 'avro-registry',
        'scan.bounded.mode' = 'unbounded',
        'scan.startup.mode' = 'earliest-offset',
        'value.format' = 'avro-registry'
    );
    EOF
}

resource "confluent_flink_statement" "insert-into-transaction-table" {
    depends_on = [
        confluent_flink_statement.create-user-transaction-table
    ]
    organization {
        id = data.confluent_organization.main.id
    }
    environment {
        id = confluent_environment.staging.id
    }
    compute_pool {
        id = confluent_flink_compute_pool.flink_pool.id
    }
    principal {
        id = confluent_service_account.app-manager.id
    }
    rest_endpoint = data.confluent_flink_region.flink_region.rest_endpoint
    credentials {
        key    = confluent_api_key.flink-api-key.id
        secret = confluent_api_key.flink-api-key.secret
    }
    properties = {
        "sql.current-catalog"  = confluent_environment.staging.display_name
        "sql.current-database" = confluent_kafka_cluster.cluster.display_name
    }
    statement = <<EOF
    INSERT INTO `user_transaction`
    SELECT after.ID as ID, 
        after.AMOUNT as AMOUNT, 
        after.RECEIVED_AT as RECEIVED_AT,
        after.IP_ADDRESS as IP_ADDRESS, 
        after.ACCOUNT_ID as ACCOUNT_ID 
    FROM `fd.SAMPLE.USER_TRANSACTION`;
    EOF
}