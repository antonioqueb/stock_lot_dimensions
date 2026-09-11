# -*- coding: utf-8 -*-
"""Candado de BIN para move lines con lote (caso testigo 20183-59 / V/107).

Odoo 19 reserva y descuenta en la ubicación LITERAL de la move line
(`_update_available_quantity` → `_gather(strict=True)`): si la línea nace
con `location_id` = SOM/Existencias (el padre) y la placa vive en un bin
hijo, el core crea un quant en el padre con cantidad 0 + reserva, al
validar lo deja negativo y el bin sigue mostrando la placa como libre
(doble disponibilidad / doble venta).

Regla única, en el punto por donde pasan TODOS los flujos (edición manual
de la entrega, reserva de taller, pick ticket, swap, Torre de Control,
remoción por lote completo):
  1. Al crear/escribir una move line con lote cuyo `location_id` es una
     ubicación interna CON hijas y sin existencia del lote ahí, la línea
     se re-apunta al bin hijo donde el lote sí tiene existencia.
  2. Al validar, una línea que sigue saliendo de una ubicación padre sin
     existencia del lote (y con existencia en un hijo) se BLOQUEA con un
     mensaje claro en vez de dejar el negativo en silencio.
"""
import logging

from odoo import api, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class StockMoveLineBinGuard(models.Model):
    _inherit = 'stock.move.line'

    # ── resolución del bin ────────────────────────────────────────────
    @api.model
    def _som_location_is_parent(self, location):
        return bool(
            location and location.usage == 'internal'
            and location.child_ids
        )

    @api.model
    def _som_lot_quants_at(self, product, lot, location, strict):
        Quant = self.env['stock.quant'].sudo()
        domain = [
            ('product_id', '=', product.id),
            ('lot_id', '=', lot.id),
            ('quantity', '>', 0),
        ]
        if strict:
            domain.append(('location_id', '=', location.id))
        else:
            domain += [
                ('location_id', 'child_of', location.id),
                ('location_id', '!=', location.id),
                ('location_id.usage', '=', 'internal'),
            ]
        return Quant.search(domain)

    @api.model
    def _som_resolve_lot_bin(self, product, lot, location, qty=0.0):
        """Bin hijo donde vive el lote cuando `location` es un padre sin
        existencia del lote. Devuelve stock.location o False (sin cambio)."""
        if not product or not lot or not location:
            return False
        storable = (product.is_storable if 'is_storable' in product._fields
                    else product.type == 'product')
        if not storable:
            return False
        if not self._som_location_is_parent(location):
            return False
        if self._som_lot_quants_at(product, lot, location, strict=True):
            return False  # el lote sí está en el padre: reserva legítima
        children = self._som_lot_quants_at(product, lot, location, strict=False)
        if not children:
            return False
        # Bin con más libre; si ninguno tiene libre suficiente, el de más
        # existencia (la reserva nativa recorta a lo disponible).
        def free(q):
            return (q.quantity or 0.0) - (q.reserved_quantity or 0.0)
        fit = children.filtered(lambda q: free(q) >= (qty or 0.0))
        best = (fit or children).sorted(lambda q: (-free(q), -(q.quantity or 0.0), q.id))[:1]
        return best.location_id

    def _som_apply_bin_guard_to_vals(self, vals, current=None):
        """Reescribe vals['location_id'] si aplica. `current` = línea
        existente (write) para completar producto/lote/ubicación."""
        if self.env.context.get('som_skip_bin_guard'):
            return vals
        lot_id = vals.get('lot_id', current.lot_id.id if current else False)
        if not lot_id:
            return vals
        loc_id = vals.get('location_id', current.location_id.id if current else False)
        prod_id = vals.get('product_id', current.product_id.id if current else False)
        if not loc_id or not prod_id:
            return vals
        state = vals.get('state', current.state if current else 'draft')
        if state in ('done', 'cancel'):
            return vals
        Loc = self.env['stock.location']
        location = Loc.browse(loc_id)
        product = self.env['product.product'].browse(prod_id)
        lot = self.env['stock.lot'].browse(lot_id)
        qty = vals.get('quantity', current.quantity if current else 0.0) or 0.0
        target = self._som_resolve_lot_bin(product, lot, location, qty)
        if target and target.id != location.id:
            _logger.info(
                '[BIN GUARD] lote %s: move line apuntaba a %s (padre); '
                're-apuntada a %s.', lot.name, location.complete_name,
                target.complete_name)
            vals = dict(vals, location_id=target.id)
        return vals

    @api.model_create_multi
    def create(self, vals_list):
        vals_list = [self._som_apply_bin_guard_to_vals(dict(v)) for v in vals_list]
        return super().create(vals_list)

    def write(self, vals):
        if vals and ('lot_id' in vals or 'location_id' in vals) \
                and not self.env.context.get('som_skip_bin_guard'):
            # Cada línea puede resolver a un bin distinto: se escribe por
            # línea solo cuando el candado cambia algo.
            plain = self.browse()
            for line in self:
                new_vals = line._som_apply_bin_guard_to_vals(dict(vals), current=line)
                if new_vals.get('location_id') != vals.get('location_id') and 'location_id' in new_vals:
                    super(StockMoveLineBinGuard, line).write(new_vals)
                else:
                    plain |= line
            if not plain:
                return True
            return super(StockMoveLineBinGuard, plain).write(vals)
        return super().write(vals)

    # ── bloqueo al validar ────────────────────────────────────────────
    def _action_done(self):
        if not self.env.context.get('som_skip_bin_guard'):
            self._som_assert_not_from_empty_parent()
        return super()._action_done()

    def _som_assert_not_from_empty_parent(self):
        problems = []
        for line in self:
            if line.state == 'cancel' or not line.lot_id or not line.product_id:
                continue
            location = line.location_id
            if not self._som_location_is_parent(location):
                continue
            if self._som_lot_quants_at(line.product_id, line.lot_id, location, strict=True):
                continue
            children = self._som_lot_quants_at(line.product_id, line.lot_id, location, strict=False)
            if not children:
                continue  # sin existencia en ningún lado: no es este defecto
            problems.append('- %s: sale de %s pero está en %s' % (
                line.lot_id.name, location.complete_name,
                ', '.join(children.mapped('location_id.complete_name'))))
        if problems:
            raise UserError(_(
                'No se puede validar: estas placas salen de una ubicación '
                'PADRE donde no existen. Odoo dejaría el padre en negativo y '
                'el bin seguiría mostrándolas como disponibles (doble '
                'disponibilidad).\n%s\n\nReasigna la placa desde el pedido '
                'de venta (selector de placas) o usa "Comprobar '
                'disponibilidad" en la operación para que la línea apunte '
                'al bin real.') % '\n'.join(problems[:20]))
