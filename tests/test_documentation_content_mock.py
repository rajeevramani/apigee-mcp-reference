#!/usr/bin/env python3
import json
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DocumentationContentMockTests(unittest.TestCase):
    def test_sample_content_preserves_markdown_diagram_and_openapi(self):
        markdown = (ROOT / "samples/payments/payment-initiation.md").read_text(encoding="utf-8")
        api_spec = (ROOT / "samples/payments/openapi.yaml").read_text(encoding="utf-8")

        self.assertIn("```mermaid", markdown)
        self.assertIn("sequenceDiagram", markdown)
        self.assertIn("Client->>Payments API", markdown)
        self.assertIn("openapi: 3.0.3", api_spec)
        self.assertIn("operationId: create_payment", api_spec)
        self.assertIn("pattern: '^\\d+\\.\\d{2}$'", api_spec)
        self.assertNotIn("pattern: '^\\\\d+\\\\.\\\\d{2}$'", api_spec)

    def test_mcp_and_reverse_contracts_expose_document_and_spec_retrieval(self):
        mcp = (ROOT / "specs/mcp-tools.openapi.yaml").read_text(encoding="utf-8")
        reverse = (ROOT / "specs/documentation-search-reverse-proxy.openapi.yaml").read_text(encoding="utf-8")

        expected = (
            (
                "/developer-intelligence/v1/documentation/sections/{api_name}/{section_id}",
                "/documentation/sections/{api_name}/{section_id}",
                "documentation_section_get",
                "DocumentationSectionResponse",
            ),
            (
                "/developer-intelligence/v1/documentation/specs/{api_name}",
                "/documentation/specs/{api_name}",
                "openapi_spec_get",
                "OpenApiSpecResponse",
            ),
        )
        for source_path, reverse_path, operation_id, response_schema in expected:
            with self.subTest(operation_id=operation_id):
                self.assertIn(f"  {source_path}:", mcp)
                self.assertIn(f"  {reverse_path}:", reverse)
                self.assertEqual(mcp.count(f"operationId: {operation_id}"), 1)
                self.assertEqual(reverse.count(f"operationId: {operation_id}"), 1)
                self.assertIn(f"    {response_schema}:", mcp)
                self.assertIn(f"    {response_schema}:", reverse)

    def test_apigee_policies_serve_the_checked_in_markdown_and_spec(self):
        policy_dir = ROOT / "apigee/documentation-search-mock/apiproxy/policies"
        expected = {
            "AM-Mock-Documentation-Section.xml": (
                "text/markdown",
                ROOT / "samples/payments/payment-initiation.md",
            ),
            "AM-Mock-OpenAPI-Spec.xml": (
                "application/yaml",
                ROOT / "samples/payments/openapi.yaml",
            ),
        }
        for filename, (content_type, source_path) in expected.items():
            with self.subTest(policy=filename):
                policy = ET.parse(policy_dir / filename).getroot()
                payload = policy.find("./Set/Payload")
                self.assertIsNotNone(payload)
                self.assertEqual(payload.get("variablePrefix"), "@")
                self.assertEqual(payload.get("variableSuffix"), "#")
                document = json.loads(payload.text or "")
                self.assertEqual(document["content_type"], content_type)
                self.assertEqual(document["content"], source_path.read_text(encoding="utf-8"))

        proxy = ET.parse(
            ROOT / "apigee/documentation-search-mock/apiproxy/proxies/default.xml"
        ).getroot()
        conditions = {flow.findtext("Condition") for flow in proxy.findall("./Flows/Flow")}
        self.assertIn(
            '(proxy.pathsuffix MatchesPath "/documentation/sections/*/*") and (request.verb = "GET")',
            conditions,
        )
        self.assertIn(
            '(proxy.pathsuffix MatchesPath "/documentation/specs/*") and (request.verb = "GET")',
            conditions,
        )

    def test_documentation_products_entitle_the_new_tools(self):
        expected_documentation = {
            "tools/call/documentation_search",
            "tools/call/documentation_section_get",
            "tools/call/openapi_spec_get",
        }
        for filename in ("mcp-all-tools.json", "mcp-documentation-only.json"):
            with self.subTest(product=filename):
                product = json.loads(
                    (ROOT / "apigee/api-products" / filename).read_text(encoding="utf-8")
                )
                operations = {
                    operation["operation"]
                    for config in product["payloadOperationGroup"]["operationConfigs"]
                    for operation in config["operations"]
                }
                self.assertTrue(expected_documentation.issubset(operations))

    def test_browser_exposes_safe_rich_and_raw_result_views(self):
        browser = (ROOT / "app/mcp-tool-browser.html").read_text(encoding="utf-8")
        self.assertIn('<script src="content-renderer.js"></script>', browser)
        self.assertIn("function renderRichResult", browser)
        self.assertIn("result-preview", browser)
        self.assertIn("Raw response", browser)


if __name__ == "__main__":
    unittest.main()
