resource "confluent_api_key" "opensearch_sink_api_key" {
    display_name = "opensearch-sink-api-key"
    description  = "API Key for OpenSearch Sink connector"
    owner {
        id          = data.terraform_remote_state.connector.outputs.service_account_id
        api_version = data.terraform_remote_state.connector.outputs.service_account_api_version
        kind        = data.terraform_remote_state.connector.outputs.service_account_kind
    }
    managed_resource {
        id          = data.terraform_remote_state.connector.outputs.kafka_cluster_id
        api_version = data.terraform_remote_state.connector.outputs.kafka_cluster_api_version
        kind        = data.terraform_remote_state.connector.outputs.kafka_cluster_kind
        environment {
            id = data.terraform_remote_state.connector.outputs.environment_id
        }
    }
}

resource "confluent_connector" "opensearch_sink" {
    depends_on = [
        confluent_api_key.opensearch_sink_api_key,
        confluent_flink_statement.flagged-user-materializer
    ]
    environment {
        id = data.terraform_remote_state.connector.outputs.environment_id
    }
    kafka_cluster {
        id = data.terraform_remote_state.connector.outputs.kafka_cluster_id
    }
    config_nonsensitive = {
        "name"                        = "opensearch-sink"
        "connector.class"             = "OpenSearchSink"
        "topics"                      = "flagged_user"
        "schema.context.name"         = "default"
        "input.data.format"           = "AVRO"
        "kafka.auth.mode"             = "KAFKA_API_KEY"
        "kafka.api.key"               = confluent_api_key.opensearch_sink_api_key.id
        "kafka.api.secret"            = confluent_api_key.opensearch_sink_api_key.secret
        "max.poll.interval.ms"        = "300000"
        "max.poll.records"            = "500"
        "tasks.max"                   = "1"
        "instance.url"                = data.terraform_remote_state.aws_resources.outputs.opensearch_details.endpoint
        "auth.type"                   = "BASIC"
        "connection.user"             = data.terraform_remote_state.aws_resources.outputs.opensearch_details.username
        "connection.password"         = data.terraform_remote_state.aws_resources.outputs.opensearch_details.password
        "opensearch.ssl.enabled"      = "false"
        "behavior.on.error"           = "FAIL"
        "indexes.num"                 = "1"
        "retry.backoff.policy"        = "EXPONENTIAL_WITH_JITTER"
        "retry.backoff.ms"            = "3000"
        "retry.on.status.codes"       = "400-"
        "max.retries"                 = "3"
        "index1.name"                 = "flagged_user"
        "index1.topic"                = "flagged_user"
        "index1.behavior.on.null.values" = "IGNORE"
        "index1.batch.size"           = "1"
        "index1.report.only.status.code.to.success.topic" = "false"
        "index1.write.method"         = "INSERT"
        "value.converter.replace.null.with.default" = "true"
        "value.converter.reference.subject.name.strategy" = "DefaultReferenceSubjectNameStrategy"
        "value.converter.schemas.enable" = "false"
        "errors.tolerance"            = "all"
        "value.converter.ignore.default.for.nullables" = "false"
        "value.converter.decimal.format" = "BASE64"
        "value.converter.value.subject.name.strategy" = "TopicNameStrategy"
        "key.converter.key.subject.name.strategy" = "TopicNameStrategy"
        "auto.restart.on.user.error"  = "true"
    }
}
