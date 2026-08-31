# -*- coding: utf-8 -*-
"""Redimensionamiento de placas (Inventario → Operaciones).

Herramienta EXCLUSIVA de administradores de inventario para corregir
las dimensiones físicas (alto × ancho) de placas en stock — una a una
o en lote — con el selector visual de placas de la casa.

Reglas duras:
- Solo stock.group_stock_manager (validado también en servidor).
- La placa debe vivir en UNA sola ubicación interna con quant positivo;
  si está repartida, se corrige a mano (jamás adivinar cómo repartir).
- El quant se ajusta a la nueva área vía ajuste de inventario nativo
  (inventory_quantity + _apply_inventory) — deja rastro contable.
- El write de x_alto/x_ancho dispara el ratchet de líneas de venta
  abiertas (stock_transit_allocation), así el Solicitado nunca queda
  por debajo del asignado.
"""
import logging

from markupsafe import Markup

from odoo import _, api, models
from odoo.exceptions import AccessError, UserError

_logger = logging.getLogger(__name__)


class StockLotResize(models.Model):
    _inherit = 'stock.lot'

    def _slr_check_manager(self):
        if not self.env.user.has_group('stock.group_stock_manager'):
            raise AccessError(_(
                'El redimensionamiento de placas es exclusivo de los '
                'administradores de inventario.'))

    @api.model
    def slr_get_plates(self, product_id):
        """Placas del producto en stock interno (para el selector visual):
        lote, ubicación, dimensiones actuales, m² y foto de portada."""
        self._slr_check_manager()
        quants = self.env['stock.quant'].sudo().search([
            ('product_id', '=', int(product_id)),
            ('location_id.usage', '=', 'internal'),
            ('quantity', '>', 0),
            ('lot_id', '!=', False),
            # sudo salta las reglas: solo compañías seleccionadas
            ('company_id', 'in', self.env.companies.ids),
        ])
        by_lot = {}
        for q in quants:
            by_lot.setdefault(q.lot_id, []).append(q)
        rows = []
        for lot, qs in by_lot.items():
            has_photo = bool(self.env['stock.lot.image'].sudo().search_count(
                [('lot_id', '=', lot.id)]))
            rows.append({
                'lot_id': lot.id,
                'lot_name': lot.name or '',
                'bloque': lot.x_bloque or 'Sin Bloque',
                'alto': lot.x_alto or 0.0,
                'ancho': lot.x_ancho or 0.0,
                'grosor': lot.x_grosor or 0.0,
                'm2': round(sum(q.quantity for q in qs), 3),
                'reserved': round(
                    sum(q.reserved_quantity for q in qs), 3),
                'locations': len(qs),
                'location_name': '/'.join(
                    (qs[0].location_id.complete_name or '').split('/')[-2:]
                ) if qs else '',
                'has_photo': has_photo,
            })
        rows.sort(key=lambda r: (r['bloque'], r['lot_name']))
        return rows

    @api.model
    def slr_apply_resizes(self, changes):
        """Aplica los cambios de dimensiones. changes = lista de
        {lot_id, alto, ancho}. Todo o nada (una transacción)."""
        self._slr_check_manager()
        if not changes:
            return {'ok': False, 'message': _('No hay cambios que aplicar.')}

        Quant = self.env['stock.quant'].sudo()
        applied = []
        for ch in changes:
            lot = self.sudo().browse(int(ch.get('lot_id') or 0))
            if not lot.exists():
                raise UserError(_('Lote inexistente en el cambio %s.') % ch)
            try:
                alto = round(float(ch.get('alto') or 0.0), 3)
                ancho = round(float(ch.get('ancho') or 0.0), 3)
            except (TypeError, ValueError):
                raise UserError(_(
                    'Dimensiones inválidas para %s.') % lot.name)
            if alto <= 0 or ancho <= 0:
                raise UserError(_(
                    '%s: alto y ancho deben ser mayores a cero (para dar '
                    'de baja una placa usa la Baja masiva, no el '
                    'redimensionamiento).') % lot.name)

            quants = Quant.search([
                ('lot_id', '=', lot.id),
                ('location_id.usage', '=', 'internal'),
                ('quantity', '>', 0),
            ])
            if not quants:
                raise UserError(_(
                    '%s ya no tiene stock interno.') % lot.name)
            if len(quants) > 1:
                raise UserError(_(
                    '%s está repartida en %s ubicaciones: unifícala antes '
                    'de redimensionar.') % (lot.name, len(quants)))

            old_alto, old_ancho = lot.x_alto or 0.0, lot.x_ancho or 0.0
            old_qty = quants.quantity
            new_qty = round(alto * ancho, 3)

            # Dimensiones primero (dispara el ratchet de ventas abiertas)
            lot.write({'x_alto': alto, 'x_ancho': ancho})

            if abs(new_qty - old_qty) > 0.0005:
                quants.with_context(
                    inventory_mode=True,
                    skip_hold_validation=True,
                ).write({'inventory_quantity': new_qty})
                quants.with_context(
                    skip_hold_validation=True)._apply_inventory()

            lot.message_post(body=Markup(
                '📐 <b>Placa redimensionada</b> por %s: '
                '%.3f × %.3f (%.3f m²) → <b>%.3f × %.3f (%.3f m²)</b>.') % (
                self.env.user.name, old_alto, old_ancho, old_qty,
                alto, ancho, new_qty))
            applied.append({'lot': lot.name, 'old': old_qty, 'new': new_qty})
            _logger.info(
                '[SLR] %s redimensionó %s: %.3fx%.3f (%.3f) -> '
                '%.3fx%.3f (%.3f)', self.env.user.login, lot.name,
                old_alto, old_ancho, old_qty, alto, ancho, new_qty)

        return {
            'ok': True,
            'count': len(applied),
            'message': _('%s placa(s) redimensionada(s).') % len(applied),
        }
