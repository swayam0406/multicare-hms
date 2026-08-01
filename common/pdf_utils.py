"""Shared PDF helper for the whole project.

Uses xhtml2pdf (pisa) to render Django templates to PDF.
"""

from io import BytesIO

from django.http import HttpResponse
from django.template.loader import get_template
from xhtml2pdf import pisa


def render_pdf(template_name: str, context: dict, filename: str) -> HttpResponse:
    """
    Render a Django template to PDF and return an HttpResponse download.

    Usage:
        return render_pdf(
            "billing/bill_pdf.html",
            {"bill": bill},
            f"bill-{bill.bill_number}.pdf",
        )
    """
    template = get_template(template_name)
    html = template.render(context)

    result = BytesIO()
    pdf_status = pisa.CreatePDF(html, dest=result, encoding="utf-8")

    if pdf_status.err:
        return HttpResponse(
            f"PDF generation failed: {pdf_status.err}",
            status=500,
        )

    response = HttpResponse(result.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def render_pdf_inline(template_name: str, context: dict, filename: str) -> HttpResponse:
    """Same as render_pdf but with inline disposition (opens in browser)."""
    response = render_pdf(template_name, context, filename)
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
