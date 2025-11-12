resource "confluent_api_key" "redshift_sink_api_key" {
    display_name = "redshift-sink-api-key"
    description  = "API Key for Redshift Sink connector"
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

resource "confluent_connector" "redshift_sink" {
    depends_on = [
        confluent_api_key.redshift_sink_api_key,
        confluent_flink_statement.flagged-user-materializer
    ]
    environment {
        id = data.terraform_remote_state.connector.outputs.environment_id
    }
    kafka_cluster {
        id = data.terraform_remote_state.connector.outputs.kafka_cluster_id
    }
    config_nonsensitive = {
        "name"                        = "redshift-sink"
        "connector.class"             = "RedshiftSink"
        "schema.context.name"         = "default"
        "input.data.format"           = "AVRO"
        "kafka.auth.mode"             = "KAFKA_API_KEY"
        "kafka.api.key"               = confluent_api_key.redshift_sink_api_key.id
        "kafka.api.secret"            = confluent_api_key.redshift_sink_api_key.secret
        "authentication.method"       = "Password"
        "aws.redshift.password"       = "Admin123456!"
        "topics"                      = "auth_user,user_transaction"
        "aws.redshift.domain"         = split(":", data.terraform_remote_state.aws_resources.outputs.redshift_endpoint)[0]
        "aws.redshift.port"           = "5439"
        "aws.redshift.user"           = "admin"
        "aws.redshift.database"       = "frauddetection"
        "db.timezone"                 = "UTC"
        "batch.size"                  = "1"
        "auto.create"                 = "true"
        "auto.evolve"                 = "false"
        "max.poll.interval.ms"        = "300000"
        "max.poll.records"            = "500"
        "tasks.max"                   = "1"
        "value.converter.decimal.format" = "BASE64"
        "value.converter.reference.subject.name.strategy" = "DefaultReferenceSubjectNameStrategy"
        "errors.tolerance"            = "all"
        "value.converter.value.subject.name.strategy" = "TopicNameStrategy"
        "key.converter.key.subject.name.strategy" = "TopicNameStrategy"
        "value.converter.ignore.default.for.nullables" = "false"
        "auto.restart.on.user.error"  = "false"
    }
}
