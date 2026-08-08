#!/usr/bin/env python3
"""Validate public and environment-rendered Apigee MCP artifacts."""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

PLACEHOLDERS = ("YOUR_APIGEE_HOSTNAME", "YOUR_APIGEE_ORG")
MCP_PRODUCT_OPERATION = re.compile(r"^tools/(?:list|call/[A-Za-z0-9._-]+)$")
EXPECTED_MCP_PRODUCTS = {
    "mcp-all-tools.json": {
        "tools/list",
        "tools/call/documentation_search",
        "tools/call/documentation_section_get",
        "tools/call/openapi_spec_get",
        "tools/call/api_catalogue_search",
    },
    "mcp-documentation-only.json": {
        "tools/list",
        "tools/call/documentation_search",
        "tools/call/documentation_section_get",
        "tools/call/openapi_spec_get",
    },
}
EXPECTED_PRODUCT_QUOTA = {"limit": "100", "interval": "1", "timeUnit": "minute"}
IPV4_OCTET = r"(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)"
GENERIC_FORBIDDEN = {
    "customer-specific organization": re.compile(r"\bA" + r"NZ\b", re.IGNORECASE),
    "literal IPv4 address": re.compile(
        rf"(?<![A-Za-z0-9_.]){IPV4_OCTET}(?:\.{IPV4_OCTET}){{3}}(?![A-Za-z0-9_.])"
    ),
}

REQUIRED = (
    "README.md",
    "LICENSE",
    "NOTICE",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "app/mcp-tool-browser.html",
    "app/content-renderer.js",
    "app/agent-simulator.js",
    "samples/payments/payment-initiation.md",
    "samples/payments/openapi.yaml",
    "specs/mcp-tools.openapi.yaml",
    "specs/documentation-search-reverse-proxy.openapi.yaml",
    "specs/api-catalogue-search-reverse-proxy.openapi.yaml",
)


class StrictishHTMLParser(HTMLParser):
    def error(self, message: str) -> None:
        raise ValueError(message)


def read_text_files(root: Path):
    for path in root.rglob("*"):
        relative_parts = path.relative_to(root).parts
        if path.is_file() and not {".git", "build", "dist", "__pycache__"}.intersection(relative_parts):
            try:
                yield path, path.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise ValueError(f"unexpected binary file: {path}") from exc


def fail(errors, message):
    errors.append(message)


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}
EXPECTED_OPERATIONS = (
    {
        "source_path": "/developer-intelligence/v1/documentation/search",
        "reverse_spec": "documentation-search-reverse-proxy.openapi.yaml",
        "reverse_path": "/documentation/search",
        "operation_id": "documentation_search",
        "parameters": {
            "query": {
                "in": "query",
                "required": "true",
                "type": "string",
                "minLength": "2",
                "maxLength": "500",
            },
            "api_name": {
                "in": "query",
                "required": "false",
                "type": "string",
                "minLength": "1",
                "maxLength": "100",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
            "limit": {
                "in": "query",
                "required": "false",
                "type": "integer",
                "minimum": "1",
                "maximum": "20",
                "default": "5",
            },
        },
        "schemas": ("DocumentationSearchResponse", "DocumentationMatch", "Problem"),
    },
    {
        "source_path": "/developer-intelligence/v1/documentation/sections/{api_name}/{section_id}",
        "reverse_spec": "documentation-search-reverse-proxy.openapi.yaml",
        "reverse_path": "/documentation/sections/{api_name}/{section_id}",
        "operation_id": "documentation_section_get",
        "parameters": {
            "api_name": {
                "in": "path",
                "required": "true",
                "type": "string",
                "minLength": "1",
                "maxLength": "100",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
            "section_id": {
                "in": "path",
                "required": "true",
                "type": "string",
                "minLength": "1",
                "maxLength": "120",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
        },
        "schemas": ("DocumentationSectionResponse", "Problem"),
    },
    {
        "source_path": "/developer-intelligence/v1/documentation/specs/{api_name}",
        "reverse_spec": "documentation-search-reverse-proxy.openapi.yaml",
        "reverse_path": "/documentation/specs/{api_name}",
        "operation_id": "openapi_spec_get",
        "parameters": {
            "api_name": {
                "in": "path",
                "required": "true",
                "type": "string",
                "minLength": "1",
                "maxLength": "100",
                "pattern": "^[A-Za-z0-9][A-Za-z0-9._-]*$",
            },
        },
        "schemas": ("OpenApiSpecResponse", "Problem"),
    },
    {
        "source_path": "/api-catalogue/v1/search",
        "reverse_spec": "api-catalogue-search-reverse-proxy.openapi.yaml",
        "reverse_path": "/search",
        "operation_id": "api_catalogue_search",
        "parameters": {
            "query": {
                "in": "query",
                "required": "true",
                "type": "string",
                "minLength": "2",
                "maxLength": "300",
            },
            "limit": {
                "in": "query",
                "required": "false",
                "type": "integer",
                "minimum": "1",
                "maximum": "10",
                "default": "5",
            },
        },
        "schemas": ("ApiCatalogueSearchResponse", "ApiCatalogueEntry", "Problem"),
    },
)


def yaml_block(text: str, header: str, indent: int) -> list[str]:
    """Return the indented YAML block after one exact header line."""
    lines = text.splitlines()
    indexes = [index for index, line in enumerate(lines) if line == header]
    if len(indexes) != 1:
        raise ValueError(f"expected one {header!r}, found {len(indexes)}")
    start = indexes[0] + 1
    end = start
    while end < len(lines):
        line = lines[end]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        end += 1
    return lines[start:end]


def yaml_subblock(lines: list[str], header: str, indent: int) -> list[str]:
    indexes = [index for index, line in enumerate(lines) if line == header]
    if len(indexes) != 1:
        raise ValueError(f"expected one {header!r}, found {len(indexes)}")
    start = indexes[0] + 1
    end = start
    while end < len(lines):
        line = lines[end]
        if line.strip() and len(line) - len(line.lstrip()) <= indent:
            break
        end += 1
    return lines[start:end]


def parse_operation(text: str, path: str) -> dict:
    path_lines = yaml_block(text, f"  {path}:", 2)
    methods = [
        line.strip()[:-1]
        for line in path_lines
        if len(line) - len(line.lstrip()) == 4
        and line.strip().endswith(":")
        and line.strip()[:-1] in HTTP_METHODS
    ]
    if methods != ["get"]:
        raise ValueError(f"{path} must expose exactly GET, got {methods}")
    operation_lines = yaml_subblock(path_lines, "    get:", 4)
    operation_text = "\n".join(operation_lines)
    operation_ids = re.findall(r"^      operationId:\s*(\S+)\s*$", operation_text, re.MULTILINE)
    if len(operation_ids) != 1:
        raise ValueError(f"{path} must contain one operationId")

    parameter_lines = yaml_subblock(operation_lines, "      parameters:", 6)
    starts = [
        index
        for index, line in enumerate(parameter_lines)
        if re.match(r"^        - name:\s*\S+\s*$", line)
    ]
    parameters = {}
    order = []
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(parameter_lines)
        chunk = parameter_lines[start:end]
        name = chunk[0].split(":", 1)[1].strip()
        if name in parameters:
            raise ValueError(f"duplicate parameter {name!r} on {path}")
        order.append(name)
        schema_index = next((i for i, line in enumerate(chunk) if line == "          schema:"), None)
        if schema_index is None:
            raise ValueError(f"parameter {name!r} on {path} has no schema")
        values = {}
        for line in chunk[1:schema_index]:
            match = re.match(r"^          (in|required):\s*(.+?)\s*$", line)
            if match:
                values[match.group(1)] = match.group(2).strip("'\"")
        for line in chunk[schema_index + 1 :]:
            match = re.match(
                r"^            (type|minLength|maxLength|minimum|maximum|default|pattern):\s*(.+?)\s*$",
                line,
            )
            if match:
                values[match.group(1)] = match.group(2).strip("'\"")
        parameters[name] = values

    success_lines = yaml_subblock(operation_lines, "        '200':", 8)
    success_refs = re.findall(r"\$ref:\s*'#/components/schemas/([^']+)'", "\n".join(success_lines))
    if len(success_refs) != 1:
        raise ValueError(f"{path} must contain one successful response schema")
    return {
        "operation_id": operation_ids[0],
        "parameters": parameters,
        "parameter_order": order,
        "success_schema": success_refs[0],
    }


def normalized_schema(text: str, name: str) -> str:
    return "\n".join(line.rstrip() for line in yaml_block(text, f"    {name}:", 4)).strip()


def main() -> int:
    repo = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=repo)
    parser.add_argument("--configured", action="store_true")
    parser.add_argument(
        "--forbidden-file",
        type=Path,
        help="optional untracked file containing one private identifier per line",
    )
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    errors = []

    if not root.is_dir():
        parser.error(f"root does not exist: {root}")

    if not args.configured:
        for relative in REQUIRED:
            if not (root / relative).is_file():
                fail(errors, f"missing required file: {relative}")

    files = list(read_text_files(root))
    combined = "\n".join(text for _, text in files)

    forbidden = dict(GENERIC_FORBIDDEN)
    if args.forbidden_file:
        forbidden_file = args.forbidden_file.expanduser().resolve()
        if not forbidden_file.is_file():
            parser.error(f"forbidden file does not exist: {forbidden_file}")
        for line_number, line in enumerate(
            forbidden_file.read_text(encoding="utf-8").splitlines(), start=1
        ):
            identifier = line.strip()
            if identifier and not identifier.startswith("#"):
                forbidden[f"private identifier from line {line_number}"] = re.compile(
                    re.escape(identifier), re.IGNORECASE
                )

    for label, pattern in forbidden.items():
        for path, text in files:
            if pattern.search(path.relative_to(root).as_posix()) or pattern.search(text):
                fail(errors, f"forbidden {label} in {path.relative_to(root)}")

    if args.configured:
        for placeholder in PLACEHOLDERS:
            if placeholder in combined:
                fail(errors, f"configured tree still contains {placeholder}")
    else:
        for placeholder in PLACEHOLDERS:
            if placeholder not in combined:
                fail(errors, f"public template is missing expected placeholder {placeholder}")

    xml_count = 0
    json_count = 0
    for path, text in files:
        suffix = path.suffix.lower()
        try:
            if suffix == ".xml":
                ET.fromstring(text)
                xml_count += 1
            elif suffix == ".json":
                document = json.loads(text)
                json_count += 1
                if "api-products" in path.parts:
                    configs = document.get("payloadOperationGroup", {}).get("operationConfigs", [])
                    configured_operations = []
                    for config in configs:
                        if config.get("apiSource") != "test-mcp":
                            fail(
                                errors,
                                f"unexpected API source in {path.relative_to(root)}: "
                                f"{config.get('apiSource')!r}",
                            )
                        if config.get("quota") != EXPECTED_PRODUCT_QUOTA:
                            fail(errors, f"unexpected product quota in {path.relative_to(root)}")
                        if len(config.get("operations", [])) != 1:
                            fail(
                                errors,
                                f"each quota entry must contain exactly one operation in "
                                f"{path.relative_to(root)}",
                            )
                        for operation in config.get("operations", []):
                            name = operation.get("operation", "")
                            configured_operations.append(name)
                            if not MCP_PRODUCT_OPERATION.fullmatch(name):
                                fail(
                                    errors,
                                    f"unsupported MCP API-product operation {name!r} "
                                    f"in {path.relative_to(root)}",
                                )
                    expected_operations = EXPECTED_MCP_PRODUCTS.get(path.name)
                    if expected_operations is None:
                        fail(errors, f"unexpected API product file: {path.relative_to(root)}")
                    elif set(configured_operations) != expected_operations or len(
                        configured_operations
                    ) != len(expected_operations):
                        fail(
                            errors,
                            f"incorrect entitlement matrix in {path.relative_to(root)}: "
                            f"expected {sorted(expected_operations)}, got {sorted(configured_operations)}",
                        )
            elif suffix == ".html":
                StrictishHTMLParser().feed(text)
        except Exception as exc:
            fail(errors, f"invalid {suffix or 'text'} in {path.relative_to(root)}: {exc}")

    pairs = (
        ("specs/mcp-tools.openapi.yaml", "apigee/mcp-discovery-proxy/apiproxy/resources/oas/mcp-tools.openapi.yaml"),
        ("specs/documentation-search-reverse-proxy.openapi.yaml", "apigee/documentation-search-mock/apiproxy/resources/oas/documentation-search-reverse-proxy.openapi.yaml"),
        ("specs/api-catalogue-search-reverse-proxy.openapi.yaml", "apigee/api-catalogue-search-mock/apiproxy/resources/oas/api-catalogue-search-reverse-proxy.openapi.yaml"),
    )
    for left, right in pairs:
        left_path, right_path = root / left, root / right
        if left_path.is_file() and right_path.is_file():
            if left_path.read_bytes() != right_path.read_bytes():
                fail(errors, f"OpenAPI copies differ: {left} != {right}")
        elif args.configured:
            fail(errors, f"missing OpenAPI pair: {left} or {right}")

    spec_root = root / "specs"
    spec_texts = {}
    for spec_path in sorted(spec_root.glob("*.openapi.yaml")):
        spec_text = spec_path.read_text(encoding="utf-8")
        spec_texts[spec_path.name] = spec_text
        relative = spec_path.relative_to(root)
        if re.search(r"^\s*-\s+url:\s+\S+/\s*$", spec_text, re.MULTILINE):
            fail(errors, f"OpenAPI server URL has a trailing slash: {relative}")
        if "name: Proprietary" in spec_text:
            fail(errors, f"OpenAPI license conflicts with the public reference: {relative}")
        if "https://www.apache.org/licenses/LICENSE-2.0.html" not in spec_text:
            fail(errors, f"OpenAPI is missing the Apache 2.0 license URL: {relative}")
        if re.search(r"^\s*scheme:\s*bearer\s*$", spec_text, re.IGNORECASE | re.MULTILINE):
            fail(errors, f"OpenAPI declares Bearer auth not implemented by the mock proxy: {relative}")
        if re.search(r"^\s*securitySchemes:\s*$", spec_text, re.MULTILINE):
            fail(errors, f"OpenAPI defines a security scheme not implemented by the mock proxy: {relative}")
        security_lines = [line for line in spec_text.splitlines() if re.match(r"^\s*security:\s*", line)]
        if security_lines != ["security: []"]:
            fail(errors, f"OpenAPI must explicitly declare the mock source unauthenticated: {relative}")

        if spec_path.name.endswith("-reverse-proxy.openapi.yaml"):
            for edge_status in ("401", "403", "429"):
                if re.search(rf"^\s*'{edge_status}':\s*$", spec_text, re.MULTILINE):
                    fail(
                        errors,
                        f"reverse-proxy OpenAPI advertises MCP-edge-only HTTP {edge_status}: {relative}",
                    )

    mcp_source = spec_root / "mcp-tools.openapi.yaml"
    if mcp_source.is_file():
        mcp_text = mcp_source.read_text(encoding="utf-8")
        if "requestBody:" in mcp_text:
            fail(errors, "MCP tool inputs must use query parameters rather than wrapped request bodies")
        for request_schema in ("DocumentationSearchRequest", "ApiCatalogueSearchRequest"):
            if request_schema in mcp_text:
                fail(errors, f"MCP source retains obsolete request schema {request_schema}")
        for selection_guidance in (
            "Use this operation when detailed API documentation is needed.",
            "Use this operation to discover which APIs or capabilities are available.",
        ):
            if selection_guidance not in mcp_text:
                fail(errors, f"MCP source is missing tool-selection guidance: {selection_guidance}")

        for contract in EXPECTED_OPERATIONS:
            reverse_text = spec_texts.get(contract["reverse_spec"])
            if reverse_text is None:
                fail(errors, f"missing reverse OpenAPI contract: specs/{contract['reverse_spec']}")
                continue
            try:
                source_operation = parse_operation(mcp_text, contract["source_path"])
                reverse_operation = parse_operation(reverse_text, contract["reverse_path"])
                if source_operation["operation_id"] != contract["operation_id"]:
                    fail(errors, f"incorrect MCP operationId for {contract['source_path']}")
                if reverse_operation["operation_id"] != contract["operation_id"]:
                    fail(errors, f"incorrect reverse operationId for {contract['reverse_path']}")
                expected_parameters = contract["parameters"]
                expected_order = list(expected_parameters)
                for label, operation in (
                    ("MCP", source_operation),
                    ("reverse", reverse_operation),
                ):
                    if operation["parameter_order"] != expected_order:
                        fail(
                            errors,
                            f"{label} parameter order differs for {contract['operation_id']}: "
                            f"expected {expected_order}, got {operation['parameter_order']}",
                        )
                    if operation["parameters"] != expected_parameters:
                        fail(
                            errors,
                            f"{label} parameter constraints differ for {contract['operation_id']}",
                        )
                if source_operation["parameters"] != reverse_operation["parameters"]:
                    fail(errors, f"MCP and reverse parameters differ for {contract['operation_id']}")
                if source_operation["success_schema"] != reverse_operation["success_schema"]:
                    fail(errors, f"successful response references differ for {contract['operation_id']}")
                for schema_name in contract["schemas"]:
                    if normalized_schema(mcp_text, schema_name) != normalized_schema(
                        reverse_text, schema_name
                    ):
                        fail(
                            errors,
                            f"shared schema {schema_name} differs for {contract['operation_id']}",
                        )
            except ValueError as exc:
                fail(errors, f"invalid aligned OpenAPI operation {contract['operation_id']}: {exc}")

    for apiproxy_dir in sorted((root / "apigee").glob("*/apiproxy")):
        descriptors = sorted(apiproxy_dir.glob("*.xml"))
        if len(descriptors) != 1:
            fail(
                errors,
                f"expected one APIProxy descriptor in {apiproxy_dir.relative_to(root)}, "
                f"found {len(descriptors)}",
            )
            continue
        descriptor_root = ET.parse(descriptors[0]).getroot()
        declared_policies = [
            name.text for name in descriptor_root.findall("./Policies/Policy") if name.text
        ]
        policy_files = sorted(path.stem for path in (apiproxy_dir / "policies").glob("*.xml"))
        if len(declared_policies) != len(set(declared_policies)):
            fail(errors, f"duplicate policy declaration in {descriptors[0].relative_to(root)}")
        if set(declared_policies) != set(policy_files):
            missing = sorted(set(policy_files) - set(declared_policies))
            stale = sorted(set(declared_policies) - set(policy_files))
            fail(
                errors,
                f"policy manifest differs in {descriptors[0].relative_to(root)}: "
                f"missing declarations {missing}, declarations without files {stale}",
            )
        referenced_policies = set()
        for endpoint_dir in ("proxies", "targets"):
            for endpoint_path in sorted((apiproxy_dir / endpoint_dir).glob("*.xml")):
                endpoint_root = ET.parse(endpoint_path).getroot()
                referenced_policies.update(
                    name.text for name in endpoint_root.findall(".//Step/Name") if name.text
                )
        undeclared_references = sorted(referenced_policies - set(declared_policies))
        if undeclared_references:
            fail(
                errors,
                f"flow references undeclared policies in {apiproxy_dir.relative_to(root)}: "
                f"{undeclared_references}",
            )
        unreferenced_policies = sorted(set(declared_policies) - referenced_policies)
        if unreferenced_policies:
            fail(
                errors,
                f"declared policy files are not referenced by a flow in "
                f"{apiproxy_dir.relative_to(root)}: {unreferenced_policies}",
            )

    source_proxy_operations = (
        (
            root / "apigee" / "documentation-search-mock" / "apiproxy" / "proxies" / "default.xml",
            "/documentation/search",
            ["RF-Missing-Query", "OAS-Validate-Request", "AM-Mock-Documentation-Response"],
            True,
        ),
        (
            root / "apigee" / "documentation-search-mock" / "apiproxy" / "proxies" / "default.xml",
            "/documentation/sections/*/*",
            ["OAS-Validate-Request", "AM-Mock-Documentation-Section"],
            False,
        ),
        (
            root / "apigee" / "documentation-search-mock" / "apiproxy" / "proxies" / "default.xml",
            "/documentation/specs/*",
            ["OAS-Validate-Request", "AM-Mock-OpenAPI-Spec"],
            False,
        ),
        (
            root / "apigee" / "api-catalogue-search-mock" / "apiproxy" / "proxies" / "default.xml",
            "/search",
            ["RF-Missing-Query", "OAS-Validate-Request", "AM-Disable-Path-Suffix"],
            True,
        ),
    )
    for proxy_path, path_suffix, expected_steps, requires_query in source_proxy_operations:
        if proxy_path.is_file():
            proxy_root = ET.parse(proxy_path).getroot()
            expected = f'(proxy.pathsuffix MatchesPath "{path_suffix}") and (request.verb = "GET")'
            matching_flows = [
                flow for flow in proxy_root.findall("./Flows/Flow") if flow.findtext("Condition") == expected
            ]
            if len(matching_flows) != 1:
                fail(errors, f"source proxy must map {path_suffix} as a GET operation")
                continue
            steps = matching_flows[0].findall("./Request/Step")
            step_names = [step.findtext("Name") for step in steps]
            if step_names != expected_steps:
                fail(
                    errors,
                    f"source proxy request policy order differs for {path_suffix}: "
                    f"expected {expected_steps}, got {step_names}",
                )
            if requires_query and (
                not steps
                or steps[0].findtext("Condition")
                != '(request.queryparam.query = null) or (request.queryparam.query = "")'
            ):
                fail(errors, f"source proxy has an incorrect missing-query condition for {path_suffix}")

    validation_policies = (
        (
            root / "apigee" / "documentation-search-mock" / "apiproxy" / "policies" / "OAS-Validate-Request.xml",
            "oas://documentation-search-reverse-proxy.openapi.yaml",
        ),
        (
            root / "apigee" / "api-catalogue-search-mock" / "apiproxy" / "policies" / "OAS-Validate-Request.xml",
            "oas://api-catalogue-search-reverse-proxy.openapi.yaml",
        ),
    )
    for policy_path, expected_resource in validation_policies:
        if not policy_path.is_file():
            fail(errors, f"missing OAS validation policy: {policy_path.relative_to(root)}")
            continue
        policy_root = ET.parse(policy_path).getroot()
        if policy_root.tag != "OASValidation":
            fail(errors, f"unexpected policy type in {policy_path.relative_to(root)}")
        if policy_root.get("enabled") != "true" or policy_root.get("continueOnError") != "false":
            fail(errors, f"OAS validation policy must fail closed: {policy_path.relative_to(root)}")
        if policy_root.findtext("OASResource") != expected_resource:
            fail(errors, f"OAS validation policy references the wrong contract: {policy_path.relative_to(root)}")
        if policy_root.findtext("./Options/ValidateMessageBody") != "false":
            fail(errors, f"GET OAS validation must not expect a message body: {policy_path.relative_to(root)}")
        if policy_root.findtext("./Options/AllowUnspecifiedParameters/Query") != "false":
            fail(errors, f"OAS validation policy must reject unspecified query parameters: {policy_path.relative_to(root)}")

    missing_query_policies = (
        root / "apigee" / "documentation-search-mock" / "apiproxy" / "policies" / "RF-Missing-Query.xml",
        root / "apigee" / "api-catalogue-search-mock" / "apiproxy" / "policies" / "RF-Missing-Query.xml",
    )
    for policy_path in missing_query_policies:
        if not policy_path.is_file():
            fail(errors, f"missing query guard policy: {policy_path.relative_to(root)}")
            continue
        policy_root = ET.parse(policy_path).getroot()
        if policy_root.tag != "RaiseFault":
            fail(errors, f"query guard must be a RaiseFault policy: {policy_path.relative_to(root)}")
            continue
        if policy_root.get("enabled") != "true" or policy_root.get("continueOnError") != "false":
            fail(errors, f"query guard must fail closed: {policy_path.relative_to(root)}")
        fault_set = policy_root.find("./FaultResponse/Set")
        if fault_set is None or fault_set.findtext("StatusCode") != "400":
            fail(errors, f"query guard must return HTTP 400: {policy_path.relative_to(root)}")
            continue
        content_type_headers = [
            header.text
            for header in fault_set.findall("./Headers/Header")
            if header.get("name") == "Content-Type"
        ]
        if content_type_headers != ["application/problem+json"]:
            fail(errors, f"query guard must return problem JSON: {policy_path.relative_to(root)}")
        payload = fault_set.find("Payload")
        if payload is None or payload.get("contentType") != "application/problem+json":
            fail(errors, f"query guard has an invalid payload content type: {policy_path.relative_to(root)}")
            continue
        try:
            problem = json.loads(payload.text or "")
        except json.JSONDecodeError:
            fail(errors, f"query guard payload is not JSON: {policy_path.relative_to(root)}")
            continue
        if problem != {
            "type": "https://example.com/problems/invalid-search-query",
            "title": "Invalid search request",
            "status": 400,
            "detail": "The query parameter is required.",
        }:
            fail(errors, f"query guard payload differs from the contract: {policy_path.relative_to(root)}")
        if policy_root.findtext("IgnoreUnresolvedVariables") != "true":
            fail(errors, f"query guard must ignore unresolved variables: {policy_path.relative_to(root)}")

    browser = root / "app" / "mcp-tool-browser.html"
    if browser.is_file():
        browser_text = browser.read_text(encoding="utf-8")
        for required in (
            "initialize",
            "tools/list",
            "tools/call",
            "x-api-key",
            "content-renderer.js",
            "agent-simulator.js",
            "Agent simulation",
            "Behind the scenes",
            "Raw response",
        ):
            if required not in browser_text:
                fail(errors, f"browser client is missing {required}")

    mock_content = (
        (
            root / "apigee" / "documentation-search-mock" / "apiproxy" / "policies" / "AM-Mock-Documentation-Section.xml",
            root / "samples" / "payments" / "payment-initiation.md",
            "text/markdown",
        ),
        (
            root / "apigee" / "documentation-search-mock" / "apiproxy" / "policies" / "AM-Mock-OpenAPI-Spec.xml",
            root / "samples" / "payments" / "openapi.yaml",
            "application/yaml",
        ),
    )
    for policy_path, sample_path, expected_content_type in mock_content:
        if not sample_path.is_file():
            if not args.configured:
                fail(errors, f"missing readable mock source: {sample_path.relative_to(root)}")
            continue
        if not policy_path.is_file():
            fail(errors, f"missing generated mock policy: {policy_path.relative_to(root)}")
            continue
        payload = ET.parse(policy_path).getroot().find("./Set/Payload")
        try:
            document = json.loads(payload.text if payload is not None else "")
        except json.JSONDecodeError:
            fail(errors, f"generated mock payload is not JSON: {policy_path.relative_to(root)}")
            continue
        if document.get("content_type") != expected_content_type:
            fail(errors, f"generated mock content type differs: {policy_path.relative_to(root)}")
        if document.get("content") != sample_path.read_text(encoding="utf-8"):
            fail(errors, f"generated mock payload is stale: {policy_path.relative_to(root)}")

    proxy_endpoint = root / "apigee" / "mcp-discovery-proxy" / "apiproxy" / "proxies" / "default.xml"
    if proxy_endpoint.is_file():
        proxy_root = ET.parse(proxy_endpoint).getroot()
        quota_steps = [
            step
            for step in proxy_root.findall(".//Step")
            if step.findtext("Name") == "Quota-PerToolLimit"
        ]
        if len(quota_steps) != 1:
            fail(errors, "MCP proxy must contain exactly one Quota-PerToolLimit step")
        else:
            condition = quota_steps[0].findtext("Condition", "")
            if "tools/list" not in condition or "tools/call/" not in condition:
                fail(
                    errors,
                    "Quota-PerToolLimit must run only for supported tools/list and tools/call/* operations",
                )

    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1

    print(f"PASS: validated {len(files)} text files ({xml_count} XML, {json_count} JSON)")
    print("PASS: generic and supplied private sanitisation patterns absent")
    print("PASS: API products contain only tools/list and tools/call/* operations")
    print("PASS: API-product entitlement matrix, source, and quotas match the reference design")
    print("PASS: API-product quota runs only for supported MCP product operations")
    print("PASS: OpenAPI source and embedded copies match")
    print("PASS: OpenAPI contracts use accurate licensing, security, and server URLs")
    print("PASS: MCP inputs use bounded GET query parameters and include tool-selection guidance")
    print("PASS: APIProxy policy manifests, files, and flow references agree")
    print("PASS: placeholder mode is correct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
