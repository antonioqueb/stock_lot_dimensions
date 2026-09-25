"""Archiva los avisos "Reserva VENCIDA" del Centro de Actividades.

Desde esta versión el vencimiento de una reserva ya no genera actividad
(solo el correo al vendedor); las que quedaron vivas se archivan en
silencio, sin mensaje en el chatter.
"""
import logging

from odoo import api, SUPERUSER_ID

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    if not version:
        return
    env = api.Environment(cr, SUPERUSER_ID, {})
    acts = env['mail.activity'].sudo().search([
        ('res_model', '=', 'stock.lot.hold.order'),
        ('summary', '=like', 'Reserva VENCIDA%'),
    ])
    if acts:
        acts.write({'active': False,
                    'feedback': 'Archivada: el aviso de reserva vencida se retiró.'})
    _logger.info('[stock_lot_dimensions] %s aviso(s) de reserva vencida archivados.', len(acts))
