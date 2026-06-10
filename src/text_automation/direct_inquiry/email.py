from __future__ import annotations

from dataclasses import dataclass
from html import escape
from importlib.resources import files

from ..accounts.gmail import InlineImage, send_email
from ..config import load_config


DIRECT_INQUIRY_SUBJECT = "Hello from Tutoring Club!"
BOOKING_URL = "https://calendar.app.google/4Vhz6x7ZGz1CQ9y66"
LOGO_URL = "https://tutoringclub.com/wp-content/uploads/2016/10/logo-horizontal-tutoring-club2.jpg"
PHONE = "(904) 268-8556"
ASSET_PACKAGE = "text_automation.direct_inquiry.assets"


@dataclass(frozen=True)
class RenderedDirectInquiryEmail:
    subject: str
    plain_text: str
    html_body: str
    inline_images: tuple[InlineImage, ...]


@dataclass(frozen=True)
class _Brand:
    footer_name: str
    signature_center: str
    address_lines: tuple[str, ...]
    website_url: str
    website_display: str
    facebook_url: str
    instagram_url: str
    business_card_content_id: str
    business_card_filename: str
    business_card_content_type: str


_BRANDS = {
    62: _Brand(
        footer_name="Tutoring Club of Jacksonville / Mandarin, FL",
        signature_center="Tutoring Club Jacksonville",
        address_lines=("10131 San Jose Boulevard", "Suite 17", "Jacksonville, FL 32257"),
        website_url="https://www.tutoringclub.com/jacksonvillefl/",
        website_display="www.tutoringclub.com/jacksonvillefl",
        facebook_url="https://www.facebook.com/TutoringClubJacksonville",
        instagram_url="https://www.instagram.com/tutoringclubjacksonville/",
        business_card_content_id="jacksonville-business-card",
        business_card_filename="jacksonville_business_card.png",
        business_card_content_type="image/png",
    ),
    95: _Brand(
        footer_name="Tutoring Club of Hodges",
        signature_center="Tutoring Club Hodges",
        address_lines=("13546 Beach Blvd. Unit #06", "Jacksonville, FL 32224"),
        website_url="https://www.tutoringclub.com/hodgesfl/",
        website_display="www.tutoringclub.com/hodgesfl",
        facebook_url="https://www.facebook.com/TutoringClubJacksonville",
        instagram_url="https://www.instagram.com/tutoringclubhodges/",
        business_card_content_id="hodges-business-card",
        business_card_filename="hodges_business_card.jpg",
        business_card_content_type="image/jpeg",
    ),
}


def render_jacksonville_hodges_direct_inquiry_email(
    *,
    parent_first_name: str,
    franchise_id: int,
) -> RenderedDirectInquiryEmail:
    brand = _brand_for(franchise_id)
    parent_first = _capitalize_name(_required_text(parent_first_name, "parent_first_name"))
    safe_parent = escape(parent_first)
    html_body = _build_html_body(parent_first_name=safe_parent, brand=brand)
    plain_text = _build_plain_text(parent_first_name=parent_first, brand=brand)
    inline_images = (_business_card_inline_image(brand),)
    return RenderedDirectInquiryEmail(
        subject=DIRECT_INQUIRY_SUBJECT,
        plain_text=plain_text,
        html_body=html_body,
        inline_images=inline_images,
    )


def send_jacksonville_hodges_direct_inquiry_email(
    *,
    parent_first_name: str,
    student_first_name: str,
    recipient_email: str,
    franchise_id: int,
) -> dict:
    franchise_id = int(franchise_id)
    recipient = _required_text(recipient_email, "recipient_email")
    franchises = {int(f.id): f for f in load_config().franchises}
    franchise = franchises.get(franchise_id)
    if franchise is None or not franchise.email:
        raise RuntimeError(f"No configured sender email found for franchise {franchise_id}")

    rendered = render_jacksonville_hodges_direct_inquiry_email(
        parent_first_name=parent_first_name,
        franchise_id=franchise_id,
    )
    result = send_email(
        sender_email=franchise.email,
        recipients=[recipient],
        subject=rendered.subject,
        body=rendered.plain_text,
        html_body=rendered.html_body,
        inline_images=rendered.inline_images,
    )
    return {
        "franchise_id": franchise_id,
        "sender_email": franchise.email,
        "recipient_email": recipient,
        "result": result,
    }


def _build_html_body(*, parent_first_name: str, brand: _Brand) -> str:
    address_html = "".join(_centered_footer_line(line) for line in brand.address_lines)
    return f"""\
<div role="main" dir="ltr" style="outline:none">
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="border-collapse:collapse;border-spacing:0px">
<tbody><tr><td>
<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:auto;border-collapse:collapse;border-spacing:0px" align="center">
<tbody><tr><td width="100%" align="center">
{_logo_section()}
{_intro_section(parent_first_name)}
{_button_section()}
{_body_section(brand)}
{_divider_section()}
{_social_section(brand)}
{_footer_section(brand, address_html)}
{_business_card_section(brand)}
</td></tr></tbody></table>
</td></tr></tbody></table>
</div>"""


def _logo_section() -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:9px 0px">
<table width="33.33333333333333%" style="vertical-align:top;border-collapse:collapse;border-spacing:0px"></table>
<table width="33.33333333333333%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="padding-left:9px;padding-right:9px">
<table cellpadding="0px" width="100%" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="word-break:break-word">
<div style="overflow:hidden"><img src="{LOGO_URL}" alt="Tutoring Club" width="127" height="36" style="width:100%;margin:0% 0px 0% 0%;height:auto;display:block;border:0px"></div>
</td></tr></tbody></table></td></tr></tbody></table>
<table width="33.33333333333333%" style="vertical-align:top;border-collapse:collapse;border-spacing:0px"></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _intro_section(parent_first_name: str) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:9px 0px">
<table width="100%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="padding-left:9px;padding-right:9px">
<table cellpadding="7px" width="100%" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="word-break:break-word">
<p dir="ltr" style="margin:0px 0pt 0pt;padding-top:0px;font-family:Arial;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;padding-left:0pt;text-indent:0pt;font-size:10.5pt;color:rgb(42,42,42);outline:none">Hi <span style="color:rgb(242,106,49);font-family:Arial;font-size:10pt;vertical-align:baseline">{parent_first_name}</span><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">,</span></p>
<br><p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;margin:6pt 0pt 0pt;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">Thank you so much for reaching out to Tutoring Club Jacksonville &mdash; I'm really glad you did!</span></p>
<br><p dir="ltr" style="margin:6pt 0pt 0px;padding-bottom:0px;font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">I'm </span><span style="color:rgb(242,106,49);font-family:Arial;font-size:10pt;vertical-align:baseline">Michele Tanner</span><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">, the admissions director, and I personally connect with every family before we get started. I'd love to schedule a quick 10&ndash;15 minute call so I can learn a little more about your student and make sure we set up the right assessment for them.</span></p>
</td></tr></tbody></table></td></tr></tbody></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _button_section() -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:0px 0px 9px 0px">
<table width="100%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="padding-left:9px;padding-right:9px">
<table cellpadding="0px" width="100%" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="word-break:break-word">
<table role="button" width="100%" border="0" cellspacing="0" cellpadding="0" style="table-layout:fixed;border-spacing:0px"><tbody><tr><td style="text-align:center;overflow:hidden;line-height:36px;text-overflow:ellipsis;background-color:rgb(64,180,229);color:rgb(28,28,28);border:1px solid rgb(64,180,229);height:27pt;font-size:12pt;font-family:Georgia;padding-left:6px;padding-right:6px;width:100%;border-radius:4px;max-width:100%;vertical-align:middle"><a href="{BOOKING_URL}" style="width:100%;text-decoration-line:none;color:rgb(28,28,28);border-color:rgb(64,180,229)" target="_blank"><span style="overflow:hidden;text-overflow:ellipsis;width:100%">Book Your Call Here</span></a></td></tr></tbody></table>
</td></tr></tbody></table></td></tr></tbody></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _body_section(brand: _Brand) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:9px 0px">
<table width="100%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="padding-left:9px;padding-right:9px">
<table cellpadding="7px" width="100%" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="word-break:break-word">
<p dir="ltr" style="margin:0px 0pt 0pt;padding-top:0px;font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">It takes less than a minute to pick a time, and you'll get an instant confirmation once you do.</span></p>
<br><p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;margin:6pt 0pt 0pt;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">In the meantime, if you have any questions at all, just reply to this email or give me a call or text at </span><span style="color:rgb(242,106,49);font-family:Arial;font-size:10pt;vertical-align:baseline">{PHONE}</span><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline"> &mdash; I'm happy to help.</span></p>
<br><p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;margin:6pt 0pt 0pt;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">Looking forward to connecting soon!</span></p>
<br><p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;margin:6pt 0pt 0pt;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">Warmly,</span></p>
<p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;margin:6pt 0pt 0pt;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(0,0,0);font-family:Arial;font-size:10pt;vertical-align:baseline">Michele Tanner, MA</span></p>
<p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;text-align:left;margin:6pt 0pt 0pt;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(42,42,42);font-family:Arial;font-size:10.5pt;vertical-align:baseline">Admissions Director, {escape(brand.signature_center)}</span></p>
<p dir="ltr" style="background-color:transparent;border-width:initial;border-style:none;border-color:initial;line-height:2.22;margin:0pt;padding:0pt;font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;text-align:left;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none"><span style="color:rgb(242,106,49);font-family:Arial;font-size:10pt;vertical-align:baseline">{PHONE}</span><span style="color:rgb(242,106,49);font-family:Arial;font-size:10.5pt;vertical-align:baseline"> </span><span style="color:rgb(0,0,0);font-family:Arial;font-size:10.5pt;vertical-align:baseline">|</span><span style="color:rgb(242,106,49);font-family:Arial;font-size:10.5pt;vertical-align:baseline"> </span><span style="color:rgb(242,106,49);font-family:Arial;font-size:10pt;vertical-align:baseline"><a href="{brand.website_url}" target="_blank">{escape(brand.website_display)}</a></span></p>
<br>
</td></tr></tbody></table></td></tr></tbody></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _divider_section() -> str:
    return """\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="padding-bottom:0px;padding-top:0px;background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:9px 0px">
<table width="100%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="padding-left:9px;padding-right:9px">
<table cellpadding="0px" width="100%" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="word-break:break-word">
<table width="100%" cellspacing="0" cellpadding="0" border="0" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="line-height:8.5px;font-size:8.5px">&nbsp;</td></tr><tr><td width="100%" style="background-color:rgb(217,217,217);line-height:2px;font-size:2px">&nbsp;</td></tr></tbody></table>
</td></tr></tbody></table></td></tr></tbody></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _social_section(brand: _Brand) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:9px 0px">
<table width="100%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="padding-left:9px;padding-right:9px">
<table cellpadding="0px" width="100%" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="word-break:break-word">
<div>{_social_icon(brand.website_url, "Link", "https://ssl.gstatic.com/atari/images/sociallinks/link_white_28dp.png")}{_social_icon(brand.facebook_url, "Facebook", "https://ssl.gstatic.com/atari/images/sociallinks/facebook_white_28dp.png")}{_social_icon(brand.instagram_url, "Instagram", "https://ssl.gstatic.com/atari/images/sociallinks/instagram_white_28dp.png")}</div>
</td></tr></tbody></table></td></tr></tbody></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _footer_section(brand: _Brand, address_html: str) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:9px 0px">
<table width="100%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" style="padding-left:9px;padding-right:9px">
<table cellpadding="7px" width="100%" style="border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="word-break:break-word">
<p dir="ltr" style="margin:0px 0pt 0pt;padding-top:0px;font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none">{escape(brand.footer_name)}</p>
{address_html}
<br><p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;margin:6pt 0pt 0pt;padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none">{PHONE}&nbsp;</p>
<br>
</td></tr></tbody></table></td></tr></tbody></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _business_card_section(brand: _Brand) -> str:
    return f"""\
<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%" style="background-size:cover;table-layout:fixed;width:100%;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%">
<table width="100%" style="margin:auto;max-width:800px;min-width:320px;border-collapse:collapse;border-spacing:0px" align="center"><tbody><tr>
<td style="min-width:12px"></td><td width="100%" style="padding:0px 0px 9px 0px">
<table width="100%" style="vertical-align:top;display:inline-table;border-collapse:collapse;border-spacing:0px"><tbody><tr><td width="100%" align="center" style="padding-left:9px;padding-right:9px;word-break:break-word">
<br clear="all"><span class="gmail_signature_prefix">-- </span><br>
<div dir="ltr" class="gmail_signature" data-smartmail="gmail_signature">
<div dir="ltr"><img src="cid:{brand.business_card_content_id}" alt="Michele Tanner business card" style="max-width:100%;height:auto;border:0px;display:inline-block"></div>
</div>
</td></tr></tbody></table>
</td><td style="min-width:12px"></td></tr></tbody></table>
</td></tr></tbody></table>"""


def _business_card_inline_image(brand: _Brand) -> InlineImage:
    data = files(ASSET_PACKAGE).joinpath(brand.business_card_filename).read_bytes()
    return InlineImage(
        content_id=brand.business_card_content_id,
        filename=brand.business_card_filename,
        content_type=brand.business_card_content_type,
        data=data,
    )


def _social_icon(href: str, alt: str, img_src: str) -> str:
    return (
        f'<a href="{href}" style="width:32px;height:32px;margin:6px;background-color:rgb(95,99,104);'
        "background-image:linear-gradient(rgb(95,99,104),rgb(95,99,104));border-radius:50%;"
        'box-sizing:content-box;overflow:hidden;display:inline-block;vertical-align:middle;line-height:0;font-size:10pt" target="_blank">'
        f'<img src="{img_src}" alt="{alt}" style="width:28px;height:28px;margin:2px;box-sizing:content-box;border:0px" width="28" height="28"></a>'
    )


def _centered_footer_line(value: str) -> str:
    return (
        '<p dir="ltr" style="font-family:Georgia;font-variant-numeric:normal;font-variant-east-asian:normal;'
        "font-variant-alternates:normal;vertical-align:baseline;line-height:1.2;margin:6pt 0pt 0pt;"
        'padding-left:0pt;text-indent:0pt;font-size:12pt;color:rgb(28,28,28);outline:none">'
        f"{escape(value)}</p>"
    )


def _build_plain_text(*, parent_first_name: str, brand: _Brand) -> str:
    address = "\n".join(brand.address_lines)
    return (
        f"Hi {parent_first_name},\n\n"
        "Thank you so much for reaching out to Tutoring Club Jacksonville - I'm really glad you did!\n\n"
        "I'm Michele Tanner, the admissions director, and I personally connect with every family before we get started. "
        "I'd love to schedule a quick 10-15 minute call so I can learn a little more about your student and make sure we set up the right assessment for them.\n\n"
        f"Book Your Call Here: {BOOKING_URL}\n\n"
        "It takes less than a minute to pick a time, and you'll get an instant confirmation once you do.\n\n"
        f"In the meantime, if you have any questions at all, just reply to this email or give me a call or text at {PHONE} - I'm happy to help.\n\n"
        "Looking forward to connecting soon!\n\n"
        "Warmly,\n"
        "Michele Tanner, MA\n"
        f"Admissions Director, {brand.signature_center}\n"
        f"{PHONE} | {brand.website_display}\n\n"
        f"{brand.footer_name}\n"
        f"{address}\n\n"
        f"{PHONE}"
    )


def _brand_for(franchise_id: int) -> _Brand:
    try:
        return _BRANDS[int(franchise_id)]
    except KeyError as exc:
        raise ValueError(f"Unsupported Jacksonville/Hodges franchise_id: {franchise_id}") from exc


def _required_text(value: str, name: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{name} is required")
    return text


def _capitalize_name(name: str) -> str:
    return " ".join(part.capitalize() for part in str(name or "").split())
