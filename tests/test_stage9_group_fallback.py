from pathlib import Path
from tempfile import TemporaryDirectory

from core.xml_tools import parse_xml, xpath_values


def test_xpath_values_group_token_fallback_resolves_edi_paths():
    xml_text = """<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<X12>
  <TS_214>
    <N1>
      <N101>SH</N101>
      <N104>SHIPPER01</N104>
    </N1>
  </TS_214>
</X12>
"""

    with TemporaryDirectory() as tmp_dir:
        xml_path = Path(tmp_dir) / "x12.xml"
        xml_path.write_text(xml_text, encoding="utf-8")
        tree, nsmap = parse_xml(str(xml_path))

        direct = xpath_values(tree, nsmap, "/X12/TS_214/N1/N104")
        grouped = xpath_values(tree, nsmap, "/X12/TS_214/GROUP_1/N1/N104")

    assert direct == ["SHIPPER01"]
    assert grouped == ["SHIPPER01"]
