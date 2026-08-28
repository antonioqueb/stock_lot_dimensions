# -*- coding: utf-8 -*-
"""Red de seguridad global: HTML en el chatter SIEMPRE se renderiza.

Desde Odoo 17, ``message_post``, ``message_notify`` y ``_message_log``
hacen ``escape(body)`` — "escape if text, keep if markup" (mail_thread.py).
Un ``str`` con ``<strong>``, ``<br/>``, ``<ul>``… se muestra LITERAL, con
las etiquetas a la vista; solo ``Markup(...)`` se pinta como HTML.

Los módulos SOM tienen cientos de cuerpos armados como ``str`` (avisos de
autorización, bitácoras de tránsito, apartados, taller…). Corregirlos uno a
uno no escala y cada módulo nuevo reincidiría. Aquí se intercepta en el
único punto común (mail.thread): si el cuerpo es ``str`` y contiene
etiquetas HTML reales, se SANEA (html_sanitize: sin scripts ni eventos) y
se entrega como ``Markup``. Texto plano y ``Markup`` pasan intactos, así
que nada de lo que ya funcionaba cambia.
"""
import re

from markupsafe import Markup

from odoo import models
from odoo.tools import html_sanitize

# Etiquetas que delatan HTML intencional (no un "<5 cm" tecleado por alguien).
_TAG_RE = re.compile(
    r'<\s*/?\s*(p|br|b|strong|i|em|u|s|ul|ol|li|div|span|a|table|thead|tbody|'
    r'tr|td|th|h[1-6]|small|hr|code|pre|blockquote|img|font|sup|sub)\b[^>]*>',
    re.I,
)
_ENTITY_RE = re.compile(r'&(nbsp|amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);', re.I)


def som_html_body(body):
    """``str`` con HTML real → ``Markup`` saneado. Cualquier otra cosa → intacta."""
    if not body or isinstance(body, Markup) or not isinstance(body, str):
        return body
    if _TAG_RE.search(body) or _ENTITY_RE.search(body):
        return Markup(html_sanitize(body))
    return body


class MailThreadHtmlGuard(models.AbstractModel):
    _inherit = 'mail.thread'

    def message_post(self, *, body='', **kwargs):
        return super().message_post(body=som_html_body(body), **kwargs)

    def message_notify(self, *, body='', **kwargs):
        return super().message_notify(body=som_html_body(body), **kwargs)

    def _message_log(self, *, body='', **kwargs):
        return super()._message_log(body=som_html_body(body), **kwargs)

    def _message_log_batch(self, bodies, **kwargs):
        bodies = {rid: som_html_body(b) for rid, b in (bodies or {}).items()}
        return super()._message_log_batch(bodies, **kwargs)
