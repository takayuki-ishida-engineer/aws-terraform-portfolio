resource "aws_apigatewayv2_api" "this" {
  name                         = var.api_name
  protocol_type                = "HTTP"
  disable_execute_api_endpoint = false
  tags                         = var.tags

  lifecycle {
    postcondition {
      condition = !local.function_reference_is_valid || self.execution_arn == format(
        "arn:%s:execute-api:%s:%s:%s", local.partition, local.region, local.account_id, self.id
      )
      error_message = "The actual API execution ARN must match the Lambda partition, Region, account and actual API ID; the root must configure the correct provider and allowed_account_ids."
    }

    postcondition {
      condition = length(self.tags_all) <= 50 && alltrue([for key, value in self.tags_all :
        length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
        can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
        try(length(value) <= 256 && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value)), false)
      ])
      error_message = "Effective API tags, including root-owned provider default_tags, must fit the 50-tag, key/value length, documented character and non-reserved/non-null limits."
    }
  }
}

resource "aws_apigatewayv2_integration" "this" {
  api_id                 = aws_apigatewayv2_api.this.id
  integration_type       = "AWS_PROXY"
  integration_method     = "POST"
  integration_uri        = var.lambda_invoke_arn
  payload_format_version = "2.0"
  connection_type        = "INTERNET"
}

resource "aws_apigatewayv2_route" "this" {
  api_id             = aws_apigatewayv2_api.this.id
  route_key          = "$default"
  authorization_type = "AWS_IAM"
  target             = "integrations/${aws_apigatewayv2_integration.this.id}"
}

resource "aws_lambda_permission" "this" {
  statement_id  = "AllowHttpApi${sha256(aws_apigatewayv2_api.this.id)}"
  action        = "lambda:InvokeFunction"
  function_name = var.lambda_function_arn
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.this.execution_arn}/$default/$default"
}

resource "aws_apigatewayv2_stage" "this" {
  api_id      = aws_apigatewayv2_api.this.id
  name        = "$default"
  auto_deploy = true
  tags        = var.tags

  access_log_settings {
    destination_arn = var.access_log_group_arn
    format = jsonencode({
      requestId          = "$context.requestId"
      routeKey           = "$context.routeKey"
      httpMethod         = "$context.httpMethod"
      status             = "$context.status"
      responseLatency    = "$context.responseLatency"
      integrationLatency = "$context.integrationLatency"
      responseLength     = "$context.responseLength"
    })
  }

  default_route_settings {
    throttling_rate_limit  = 10
    throttling_burst_limit = 20
  }

  lifecycle {
    postcondition {
      condition = length(self.tags_all) <= 50 && alltrue([for key, value in self.tags_all :
        length(key) >= 1 && length(key) <= 128 && !startswith(lower(key), "aws:") &&
        can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]+$", key)) &&
        try(length(value) <= 256 && can(regex("^[\\p{L}\\p{Z}\\p{N}_.:/=+@-]*$", value)), false)
      ])
      error_message = "Effective stage tags, including root-owned provider default_tags, must fit the 50-tag, key/value length, documented character and non-reserved/non-null limits."
    }
  }

  depends_on = [aws_apigatewayv2_route.this, aws_lambda_permission.this]
}
