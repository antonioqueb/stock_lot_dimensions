"""Normaliza x_unidad_del_producto a Placa / Formato / Pieza / Servicio.

Productos capturados como 'PIEZAS', 'PZ' o 'PLACA' rompían el Procesar PL
(x_tipo del lote solo acepta placa/formato/pieza). Caso: C177.
"""
import logging

from odoo import api, SUPERUSER_ID

from odoo.addons.stock_lot_dimensions.models.product_template import som_normalize_unit

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {'active_test': False})
    Tmpl = env['product.template'].with_context(active_test=False)
    fixed = 0
    for tmpl in Tmpl.search([('x_unidad_del_producto', '!=', False)]):
        new = som_normalize_unit(tmpl.x_unidad_del_producto)
        if new != tmpl.x_unidad_del_producto:
            _logger.info('[stock_lot_dimensions] Unidad de %s (id %s): %r -> %r',
                         tmpl.name, tmpl.id, tmpl.x_unidad_del_producto, new)
            tmpl.write({'x_unidad_del_producto': new})
            fixed += 1
    _logger.info('[stock_lot_dimensions] %s producto(s) con unidad normalizada.', fixed)
