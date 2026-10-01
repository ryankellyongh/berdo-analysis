"""The PDF summary always fits on one page."""
import io


def test_pdf_is_one_page():
    try:
        import reportlab  # noqa: F401
        from pypdf import PdfReader
    except ImportError:
        return  # PDF libraries not installed; nothing to test
    from berdo.emissions import get_compliance_pathways
    from berdo.pdf_export import build_building_summary_pdf
    periods = [{"period": p, "limit": 5.3, "gap": 0.7, "status": "Over limit", "acp": 8190}
               for p in ["2025–29", "2030–34", "2035–39", "2040–44", "2045–49", "2050+"]]
    pdf = build_building_summary_pdf({
        "address": "1 Example St", "owner": "OWNER & SONS LLC", "data_year": "2025 reporting year (2024 energy use)",
        "facts": [("Item " + str(i), "Value", "Reported") for i in range(10)],
        "periods": periods, "limit_basis": "Default limit.", "notes": ["Note " * 30] * 8,
        "pathways": get_compliance_pathways({"over_now": True, "owner_building_count": 3, "elec_share": 0.3}),
    })
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 1
