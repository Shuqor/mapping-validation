from lxml import etree

def parse_xml(path: str):
    parser = etree.XMLParser(remove_blank_text=True, recover=True)
    tree = etree.parse(path, parser)
    root = tree.getroot()
    default_ns = root.nsmap.get(None)
    nsmap = {"ns": default_ns} if default_ns else {}
    return tree, nsmap

def rewrite_xpath_for_default_ns(xpath: str, nsmap: dict):
    """
    If XML has a default namespace, lxml requires a prefix in XPath.
    Example: /status/ediCustomerNumber -> /ns:status/ns:ediCustomerNumber
    Keeps predicates like detail[@description="x"] and attributes like @type.
    """
    if not nsmap or "ns" not in nsmap or not xpath.startswith("/"):
        return xpath

    parts = xpath.split("/")
    out = []
    for p in parts:
        if p == "":
            out.append("")
            continue
        if p.startswith("@") or p.startswith("ns:") or p.startswith("*") or p.startswith("text()"):
            out.append(p)
            continue

        # Handles predicates like: detail[@description="x"]
        if p[0].isalpha():
            out.append("ns:" + p)
        else:
            out.append(p)

    return "/".join(out)

def xpath_values(tree, nsmap, xpath: str):
    """
    Return list of string values from evaluating XPath against the XML tree.
    """
    if not xpath:
        return []

    if xpath == "/status/@xmlns":
        namespace = tree.getroot().nsmap.get(None)
        return [namespace] if namespace else []

    xp = rewrite_xpath_for_default_ns(xpath, nsmap)
    try:
        result = tree.xpath(xp, namespaces=nsmap)
    except etree.XPathEvalError:
        return []

    if isinstance(result, (bool, str, int, float)):
        return [str(result).strip()]

    values = []
    for item in result:
        if isinstance(item, etree._Element):
            values.append((item.text or "").strip())
        else:
            values.append(str(item).strip())
    return values
