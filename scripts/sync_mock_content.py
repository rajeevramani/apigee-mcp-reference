#!/usr/bin/env python3
"""Synchronize readable sample files into deterministic Apigee mock policies."""

import json
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
POLICIES = ROOT / "apigee/documentation-search-mock/apiproxy/policies"


def policy_xml(name: str, document: dict) -> str:
    payload = escape(json.dumps(document, indent=2, ensure_ascii=False))
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<AssignMessage name="{name}" continueOnError="false" enabled="true">
  <Set>
    <StatusCode>200</StatusCode>
    <ReasonPhrase>OK</ReasonPhrase>
    <Headers>
      <Header name="Content-Type">application/json</Header>
    </Headers>
    <Payload contentType="application/json" variablePrefix="@" variableSuffix="#">{payload}</Payload>
  </Set>
  <IgnoreUnresolvedVariables>true</IgnoreUnresolvedVariables>
  <AssignTo createNew="true" transport="http" type="response"/>
</AssignMessage>
'''


def main() -> None:
    markdown = (ROOT / "samples/payments/payment-initiation.md").read_text(encoding="utf-8")
    specification = (ROOT / "samples/payments/openapi.yaml").read_text(encoding="utf-8")

    outputs = {
        "AM-Mock-Documentation-Section.xml": (
            "AM-Mock-Documentation-Section",
            {
                "api_name": "payments",
                "document_id": "payments-guide",
                "section_id": "payment-initiation",
                "title": "Payment initiation flow",
                "content_type": "text/markdown",
                "content": markdown,
            },
        ),
        "AM-Mock-OpenAPI-Spec.xml": (
            "AM-Mock-OpenAPI-Spec",
            {
                "api_name": "payments",
                "format": "openapi-3.0-yaml",
                "content_type": "application/yaml",
                "content": specification,
            },
        ),
    }
    for filename, (name, document) in outputs.items():
        (POLICIES / filename).write_text(policy_xml(name, document), encoding="utf-8")


if __name__ == "__main__":
    main()
