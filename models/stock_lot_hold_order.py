# -*- coding: utf-8 -*-
# models/stock_lot_hold_order.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare
from .utils.business_days import BusinessDaysCalculator
from .som_date_format import som_format_date
import logging

_logger = logging.getLogger(__name__)


class StockLotHoldOrder(models.Model):
    _name = 'stock.lot.hold.order'
    _description = 'Orden de Reserva de Lotes'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Número', required=True, readonly=True, default='/', copy=False)
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        required=True,
        default=lambda self: self.env.company,
        readonly=True,
    )
    partner_id = fields.Many2one('res.partner', string='Cliente', required=True, tracking=True)
    delivery_address = fields.Text(string='Dirección de Entrega', tracking=True)
    user_id = fields.Many2one(
        'res.users',
        string='Vendedor',
        default=lambda self: self.env.user,
        required=True,
        tracking=True,
    )
    project_id = fields.Many2one('project.project', string='Proyecto', tracking=True)
    arquitecto_id = fields.Many2one(
        'res.partner',
        string='Embajador',
        domain=[('x_es_arquitecto', '=', True)],
        tracking=True,
    )
    fecha_orden = fields.Datetime(
        string='Fecha Orden',
        default=fields.Datetime.now,
        required=True,
        readonly=True,
    )
    fecha_expiracion = fields.Datetime(string='Fecha Expiración', required=True, readonly=True)
    state = fields.Selection([
        ('draft', 'Borrador'),
        ('confirmed', 'Confirmada'),
        ('done', 'Finalizada'),
        ('cancel', 'Cancelada'),
    ], string='Estado', default='draft', required=True, tracking=True)

    hold_line_ids = fields.One2many(
        'stock.lot.hold.order.line',
        'order_id',
        string='Líneas de Reserva',
    )
    notas = fields.Text(string='Notas')
    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        required=True,
        default=lambda self: self.env.company.currency_id,
        tracking=True,
    )
    sale_order_id = fields.Many2one(
        'sale.order',
        string='Orden de Venta Generada',
        readonly=True,
        tracking=True,
    )

    # IMPORTANTE:
    # Se deja SIN store para que el total superior refresque correctamente en formulario.
    total_placas = fields.Integer(string='Total Placas', compute='_compute_totals')
    total_m2 = fields.Float(string='Total m²', compute='_compute_totals', digits=(10, 2))
    total_con_precio = fields.Monetary(
        string='Total General',
        compute='_compute_totals',
        currency_field='currency_id',
    )

    dias_restantes = fields.Integer(string='Días Restantes', compute='_compute_dias_restantes')

    @api.onchange('partner_id')
    def _onchange_partner_id(self):
        # La dirección de entrega se toma del contacto de tipo "Dirección de
        # entrega" del cliente. Si el cliente no tiene uno, se deja vacío
        # (no se usa la dirección propia del cliente).
        self.delivery_address = self._get_delivery_address_text(self.partner_id)

    def _get_delivery_address_text(self, partner):
        """Texto de la dirección de entrega tomada del contacto de tipo
        'delivery' del cliente. Devuelve '' si no existe tal contacto."""
        if not partner:
            return ''
        delivery = self._resolve_delivery_partner(partner)
        if not delivery:
            _logger.info(
                "[HOLD] Cliente %s (id=%s) sin contacto de entrega; "
                "delivery_address vacío.", partner.display_name, partner.id
            )
            return ''
        text = self._format_partner_address(delivery)
        _logger.info(
            "[HOLD] Cliente %s -> contacto entrega %s (id=%s); "
            "delivery_address=%r", partner.display_name,
            delivery.display_name, delivery.id, text
        )
        return text

    def _resolve_delivery_partner(self, partner):
        """Resuelve el contacto hijo de tipo entrega del cliente.

        1) Usa address_get(['delivery']) — la forma canónica del sistema, que
           recorre la jerarquía. Si devuelve un contacto distinto del cliente,
           ése es el contacto de entrega.
        2) Si address_get devuelve el propio cliente (no hay hijo de entrega),
           busca explícitamente entre los hijos uno de tipo 'delivery'.

        Devuelve un recordset vacío si el cliente no tiene contacto de entrega.
        """
        Partner = self.env['res.partner']
        delivery_id = False
        try:
            delivery_id = (partner.address_get(['delivery']) or {}).get('delivery')
        except Exception as exc:  # noqa: BLE001
            _logger.warning("[HOLD] address_get falló para %s: %s", partner.id, exc)

        if delivery_id and delivery_id != partner.id:
            return Partner.browse(delivery_id)

        return partner.child_ids.filtered(lambda c: c.type == 'delivery')[:1]

    @staticmethod
    def _format_partner_address(delivery):
        """Texto completo de la dirección de entrega, igual que el wizard de
        entregas (_som_get_delivery_address_text).

        Concatena el nombre del contacto de entrega + su dirección completa
        (calle, calle2, ciudad, estado, C.P., país con el formato del país).
        Si el contacto de entrega no tiene su propia calle/ciudad/CP, usa la
        dirección del contacto comercial (padre).
        """
        addr_partner = delivery
        if not (delivery.street or delivery.street2 or delivery.city or delivery.zip):
            commercial = delivery.commercial_partner_id
            if commercial and commercial != delivery and (
                commercial.street or commercial.city or commercial.zip
            ):
                addr_partner = commercial

        lines = [delivery.name or '']
        address = (addr_partner._display_address(without_company=True) or '').strip()
        if address:
            lines.append(address)
        return '\n'.join(part for part in lines if part).strip()

    @api.depends(
        'hold_line_ids',
        'hold_line_ids.product_id',
        'hold_line_ids.product_id.type',
        'hold_line_ids.lot_ids',
        'hold_line_ids.lot_count',
        'hold_line_ids.cantidad_m2',
        'hold_line_ids.precio_unitario',
        'hold_line_ids.precio_total',
    )
    def _compute_totals(self):
        for order in self:
            total_placas = 0
            total_m2 = 0.0
            total_general = 0.0

            for line in order.hold_line_ids:
                if line.product_id and line.product_id.type != 'service':
                    total_placas += len(line.lot_ids)

                total_m2 += line.cantidad_m2 or 0.0
                total_general += line.precio_total or 0.0

            order.total_placas = total_placas
            order.total_m2 = total_m2
            order.total_con_precio = total_general

    @api.onchange('hold_line_ids')
    def _onchange_hold_line_ids_recompute_totals(self):
        # Fuerza refresco visual en la cabecera del formulario
        self._compute_totals()

    # ── Ciclo de vencimiento ──
    # 1er vencimiento: franja roja, el material SE MANTIENE.
    # Renovación: la franja se quita (el contador se conserva).
    # 2º vencimiento: se elimina TODO el material de la reserva dejando
    # el detalle en el log (chatter).
    x_expired_count = fields.Integer(
        string='Veces vencida', default=0, copy=False, readonly=True,
        tracking=True)
    x_expired_flag = fields.Boolean(
        string='En ciclo vencido', default=False, copy=False,
        help='True mientras la orden está vencida sin renovar; se apaga al renovar.')
    x_is_expired = fields.Boolean(
        string='Vencida', compute='_compute_x_is_expired')

    def _compute_x_is_expired(self):
        ahora = fields.Datetime.now()
        for order in self:
            order.x_is_expired = bool(
                order.state == 'confirmed'
                and order.fecha_expiracion
                and order.fecha_expiracion <= ahora)

    def _som_process_expiration_cycle(self):
        """Procesa el vencimiento de órdenes confirmadas (llamado por el
        cron de holds ANTES de expirar holds sueltos). Devuelve los ids de
        holds que deben MANTENERSE activos (1er vencimiento)."""
        kept_hold_ids = set()
        for order in self:
            active_holds = order.hold_line_ids.mapped('hold_ids').filtered(
                lambda h: h.estado == 'activo')

            if not order.x_expired_flag:
                order.x_expired_flag = True
                order.x_expired_count += 1
                if order.x_expired_count == 1:
                    order.message_post(body=(
                        '⚠ RESERVA VENCIDA (1ª vez). El material se '
                        'mantiene apartado. Renueva para quitar la franja; '
                        'al SEGUNDO vencimiento el material se eliminará '
                        'automáticamente de la reserva.'))

            if order.x_expired_count <= 1:
                # Primer vencimiento: el material se mantiene.
                kept_hold_ids.update(active_holds.ids)
                continue

            # Segundo vencimiento: registrar el detalle y eliminar TODO el
            # material. El log del chatter queda como único rastro.
            if order.hold_line_ids:
                detalle = []
                for line in order.hold_line_ids:
                    lots = ', '.join(line.lot_ids.mapped('name')) or '—'
                    detalle.append(
                        '• %s — %.2f m² — lotes: %s — total %s%.2f' % (
                            line.product_id.display_name or '',
                            line.cantidad_m2 or 0.0,
                            lots,
                            (order.currency_id.symbol or '$'),
                            line.precio_total or 0.0,
                        ))
                order.message_post(body=(
                    '⛔ SEGUNDO VENCIMIENTO: se eliminó todo el material '
                    'de la reserva. Detalle de lo eliminado:\n%s'
                ) % '\n'.join(detalle))
                order.hold_line_ids.unlink()
        return kept_hold_ids

    @api.depends('fecha_expiracion', 'state')
    def _compute_dias_restantes(self):
        ahora = fields.Datetime.now()
        for order in self:
            if order.state != 'confirmed' or not order.fecha_expiracion or order.fecha_expiracion <= ahora:
                order.dias_restantes = 0
            else:
                order.dias_restantes = BusinessDaysCalculator.count_business_days(
                    ahora,
                    order.fecha_expiracion,
                )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', '/') == '/':
                vals['name'] = self.env['ir.sequence'].next_by_code('stock.lot.hold.order') or '/'

            # Auto-calcular fecha_expiracion incluso cuando fecha_orden no viene en vals
            if 'fecha_expiracion' not in vals:
                fecha_base = (
                    fields.Datetime.to_datetime(vals['fecha_orden'])
                    if vals.get('fecha_orden')
                    else fields.Datetime.now()
                )
                vals['fecha_expiracion'] = BusinessDaysCalculator.add_business_days(fecha_base, 5)

        return super().create(vals_list)

    def unlink(self):
        # Borrar la orden borra sus líneas por cascada SQL (sin pasar por el
        # unlink de la línea), así que los holds activos se liberan aquí.
        self._release_related_holds()
        return super().unlink()

    def _release_related_holds(self):
        for order in self:
            active_holds = self.env['stock.lot.hold']
            for line in order.hold_line_ids:
                active_holds |= line.hold_ids.filtered(lambda h: h.estado == 'activo')

            if active_holds:
                active_holds.write({'estado': 'cancelado'})
                order.message_post(body=f"Se liberaron {len(active_holds)} apartados automáticamente.")

    def _find_quant_for_lot(self, lot, company_id):
        """
        Busca quant con stock positivo para un lote.
        Primero en ubicaciones internas, luego en tránsito.
        """
        quant = self.env['stock.quant'].search([
            ('lot_id', '=', lot.id),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
            ('company_id', '=', company_id),
        ], limit=1)

        if quant:
            return quant

        quant = self.env['stock.quant'].search([
            ('lot_id', '=', lot.id),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'transit'),
            ('company_id', '=', company_id),
        ], limit=1)

        return quant

    def action_confirm(self):
        for order in self:
            # Guard de estado: sin esto, una orden cancelada podía re-confirmarse
            # (vía RPC/acción de servidor) quedando "confirmada" sin crear ningún
            # hold real (bloqueo fantasma), porque los lotes se saltaban por
            # tener holds viejos cancelados/expirados.
            if order.state != 'draft':
                raise UserError('Solo puedes confirmar órdenes de reserva en borrador.')

            if not order.hold_line_ids:
                raise UserError('Debe agregar al menos una línea a la reserva.')

            for line in order.hold_line_ids:
                if line.product_id.type == 'service':
                    continue

                if not line.lot_ids:
                    raise UserError(f'La línea de {line.product_id.display_name} no tiene placas seleccionadas.')

                # Solo un hold ACTIVO cuenta como "ya apartado": los cancelados
                # o expirados no reservan nada y el lote debe apartarse de nuevo.
                already_held_lot_ids = line.hold_ids.filtered(
                    lambda h: h.estado == 'activo'
                ).mapped('lot_id').ids

                for lot in line.lot_ids:
                    if lot.id in already_held_lot_ids:
                        continue
                    order._create_hold_for_line_lot(line, lot)

            order.state = 'confirmed'

    def _create_hold_for_line_lot(self, line, lot):
        """Crea (y liga a la línea) el hold de una placa, con las mismas
        validaciones de la confirmación: quant con stock y placa sin hold
        activo de otro documento. Lo usan action_confirm y la sincronización
        de holds cuando se agregan placas a una orden ya confirmada."""
        self.ensure_one()
        self._som_assert_lots_not_committed_to_sale(lot)
        quant = self._find_quant_for_lot(lot, self.company_id.id)
        if not quant:
            raise UserError(f'El lote {lot.name} no tiene stock disponible para reservar.')

        existing = self.env['stock.lot.hold'].search([
            ('quant_id', '=', quant.id),
            ('estado', '=', 'activo'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        if existing:
            raise UserError(
                f'El lote {lot.name} ya tiene reserva activa para {existing.partner_id.name}.'
            )

        notas_hold = f'Orden: {self.name}\n'
        if self.notas:
            notas_hold += f'\n{self.notas}'

        hold = self.env['stock.lot.hold'].create({
            'lot_id': lot.id,
            'quant_id': quant.id,
            'partner_id': self.partner_id.id,
            'user_id': self.user_id.id,
            'project_id': self.project_id.id if self.project_id else False,
            'arquitecto_id': self.arquitecto_id.id if self.arquitecto_id else False,
            'fecha_inicio': self.fecha_orden,
            'fecha_expiracion': self.fecha_expiracion,
            'notas': notas_hold,
            'company_id': self.company_id.id,
        })
        line.write({'hold_ids': [(4, hold.id)]})
        return hold

    def action_cancel(self):
        self._release_related_holds()
        self.write({'state': 'cancel'})

    def action_done(self):
        self._release_related_holds()
        self.write({'state': 'done'})

    def _som_assert_lots_not_committed_to_sale(self, lots):
        """Un lote que ya vive en una orden de venta ACTIVA (borrador,
        enviada o confirmada) no puede apartarse, confirmarse ni renovarse
        en una reserva: truena nombrando lote → orden → cliente. Cierra el
        hueco de renovar una reserva expirada cuyo material ya se vendió."""
        self.ensure_one()
        Sol = self.env['sale.order.line'].sudo()
        if 'lot_ids' not in Sol._fields or not lots:
            return
        sols = Sol.search([
            ('lot_ids', 'in', lots.ids),
            ('order_id.state', 'in', ('draft', 'sent', 'sale')),
        ])
        if not sols:
            return
        conflicts = set()
        for sol in sols:
            for lot in (sol.lot_ids & lots):
                conflicts.add('• %s → %s (%s)' % (
                    lot.name, sol.order_id.name,
                    sol.order_id.partner_id.display_name or ''))
        if conflicts:
            raise UserError(
                'No se puede reservar ni renovar: estos lotes ya están en '
                'una orden de venta activa:\n%s\n\n'
                'Quita esos lotes de la reserva, o libéralos de la venta '
                'primero.' % '\n'.join(sorted(conflicts)))

    def action_renew(self):
        """Renueva la orden completa: extiende los holds activos y REACTIVA los
        expirados (si su placa sigue libre).

        Fixes:
        - Antes llamaba `action_renovar_hold()` (ensure_one) sobre un recordset
          de N holds → "Expected singleton" con 2+ placas y también con 0.
        - Los holds 'expirado' eran un callejón sin salida: convertir exigía
          todo activo, renovar solo tocaba activos y nada los reactivaba.
        """
        Hold = self.env['stock.lot.hold']

        for order in self:
            if order.state != 'confirmed':
                raise UserError('Solo puede renovar órdenes confirmadas.')

            nueva_expiracion = BusinessDaysCalculator.get_expiration_date(days=5)
            all_holds = order.hold_line_ids.mapped('hold_ids')

            active_holds = all_holds.filtered(lambda h: h.estado == 'activo')
            expired_holds = all_holds.filtered(lambda h: h.estado == 'expirado')

            if not active_holds and not expired_holds:
                raise UserError(
                    'La orden no tiene reservas activas ni expiradas que renovar. '
                    'Cancélala y crea una nueva.'
                )

            # Material ya vendido ⇒ la renovación completa se rechaza (no
            # se renueva "lo que se pueda": el vendedor debe depurar la
            # orden de reserva primero).
            order._som_assert_lots_not_committed_to_sale(
                order.hold_line_ids.mapped('lot_ids'))

            # Reactivar expirados solo si nadie más apartó la placa mientras
            # tanto (el índice único de holds activos respalda contra carreras).
            for hold in expired_holds:
                conflict = Hold.search([
                    ('quant_id', '=', hold.quant_id.id),
                    ('estado', '=', 'activo'),
                    ('id', '!=', hold.id),
                ], limit=1)
                if conflict:
                    raise UserError(
                        f'No se puede renovar: la placa {hold.lot_id.name} expiró y '
                        f'ya fue apartada por {conflict.partner_id.name}. '
                        'Quítala de la orden o cancela la orden.'
                    )
                if not hold.quant_id or (hold.quant_id.quantity or 0.0) <= 0:
                    raise UserError(
                        f'No se puede renovar: la placa {hold.lot_id.name} ya no '
                        'tiene existencias. Quítala de la orden.'
                    )

            if active_holds:
                active_holds.write({'fecha_expiracion': nueva_expiracion})
            if expired_holds:
                expired_holds.write({
                    'estado': 'activo',
                    'fecha_expiracion': nueva_expiracion,
                })

            order.fecha_expiracion = nueva_expiracion
            order.x_expired_flag = False
            order.message_post(body=(
                f'Reserva renovada hasta {som_format_date(nueva_expiracion, with_time=True)}: '
                f'{len(active_holds)} hold(s) extendido(s)'
                + (f', {len(expired_holds)} reactivado(s).' if expired_holds else '.')
            ))

    def action_convert_to_sale_order(self):
        self.ensure_one()

        # Candado de fila contra doble conversión concurrente (dos pestañas /
        # dos usuarios): la segunda transacción espera aquí y, al liberarse,
        # re-lee los guards con datos ya confirmados por la primera.
        self.env.cr.execute(
            "SELECT id FROM stock_lot_hold_order WHERE id = %s FOR UPDATE",
            (self.id,),
        )
        self.invalidate_recordset(['state', 'sale_order_id'])

        if self.state != 'confirmed':
            raise UserError('Solo puede convertir órdenes de reserva confirmadas.')
        if self.sale_order_id:
            raise UserError('Esta orden de reserva ya generó una orden de venta.')
        if not self.hold_line_ids:
            raise UserError('No hay líneas de reserva para convertir.')

        for line in self.hold_line_ids:
            if line.product_id.type == 'service':
                continue
            inactive = line.hold_ids.filtered(lambda h: h.estado != 'activo')
            if inactive:
                raise UserError('Hay reservas que ya no están activas. Renueve antes de convertir.')

        product_groups = {}
        services_list = []

        for line in self.hold_line_ids:
            if line.product_id.type == 'service':
                services_list.append({
                    'product_id': line.product_id.id,
                    'quantity': line.cantidad_m2,
                    'price_unit': line.precio_unitario or 0.0,
                    'mask_name': line.x_mask_name or '',
                })
                continue

            pid = line.product_id.id
            if pid not in product_groups:
                product_groups[pid] = {
                    'product_id': pid,
                    'quantity': 0,
                    'selected_lots': [],
                    'price_unit': line.precio_unitario or 0.0,
                    'mask_name': line.x_mask_name or '',
                }
            # La MÁSCARA viaja a la orden de venta: si varias líneas del
            # mismo producto traen máscara, gana la primera no vacía.
            if line.x_mask_name and not product_groups[pid].get('mask_name'):
                product_groups[pid]['mask_name'] = line.x_mask_name

            for lot in line.lot_ids:
                quant = self.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('quantity', '>', 0),
                    ('location_id.usage', '=', 'internal'),
                    ('company_id', '=', self.company_id.id),
                ], limit=1)

                if not quant:
                    # Distinguir "en tránsito" de "sin stock": el hold pudo
                    # confirmarse sobre una placa en tránsito, pero la venta
                    # solo puede reservar stock interno. Mensaje honesto.
                    transit_quant = self.env['stock.quant'].search([
                        ('lot_id', '=', lot.id),
                        ('quantity', '>', 0),
                        ('location_id.usage', '=', 'transit'),
                        ('company_id', '=', self.company_id.id),
                    ], limit=1)
                    if transit_quant:
                        raise UserError(
                            f'El lote {lot.name} está EN TRÁNSITO (aún no llega al '
                            'almacén). Convierte la reserva cuando el material haya '
                            'sido recibido, o renueva el hold mientras tanto.'
                        )
                    raise UserError(f'El lote {lot.name} ya no tiene stock disponible.')

                product_groups[pid]['quantity'] += quant.quantity
                product_groups[pid]['selected_lots'].append(quant.id)

            # Material sin existencia / "mandar a pedir": no tiene placas pero sí
            # una cantidad capturada manualmente. Esa cantidad debe propagarse a
            # la línea de la SO y la línea debe marcarse para envío a compra.
            if self._hold_line_is_backorder(line):
                product_groups[pid]['quantity'] += line.cantidad_m2 or 0.0
                product_groups[pid]['to_be_purchased'] = True

        products = list(product_groups.values())

        notes = self.notas or ''

        pricelist = self.env['product.pricelist'].search([
            ('name', '=', self.currency_id.name)
        ], limit=1)

        if not pricelist:
            raise UserError(f'No se encontró lista de precios para {self.currency_id.name}')

        try:
            result = self.env['sale.order'].with_context(
                from_hold_order=True,
                hold_order_id=self.id,
            ).create_from_shopping_cart(
                partner_id=self.partner_id.id,
                products=products,
                services=services_list,
                notes=notes,
                pricelist_id=pricelist.id,
                apply_tax=True,
                project_id=self.project_id.id if self.project_id else None,
                architect_id=self.arquitecto_id.id if self.arquitecto_id else None,
            )

            if result.get('needs_authorization'):
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '⚠️ Autorización Requerida',
                        'message': result['message'],
                        'type': 'warning',
                        'sticky': True,
                    }
                }

            if result.get('success'):
                sale_order = self.env['sale.order'].browse(result['order_id'])
                self.write({'sale_order_id': sale_order.id, 'state': 'done'})

                for line in self.hold_line_ids:
                    for hold in line.hold_ids.filtered(lambda h: h.estado == 'activo'):
                        hold.action_cancelar_hold()

                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': '✅ Orden de Venta Creada',
                        'message': f'Orden {sale_order.name} creada exitosamente',
                        'type': 'success',
                        'sticky': False,
                        'next': {
                            'type': 'ir.actions.act_window',
                            'res_model': 'sale.order',
                            'res_id': sale_order.id,
                            'views': [[False, 'form']],
                            'target': 'current',
                        }
                    }
                }

        except UserError:
            # Los errores de negocio legibles se propagan tal cual (antes se
            # doble-envolvían perdiendo claridad).
            raise
        except Exception as e:
            # Errores inesperados: dejar el traceback completo en el log antes
            # de traducirlos a un mensaje de usuario.
            _logger.exception(
                '[HOLD ORDER] Error inesperado al convertir %s a orden de venta.',
                self.name,
            )
            raise UserError(f'Error al crear orden de venta: {str(e)}')

    # ==================== HELPERS PARA REPORTES ====================
    # Orden en que aparecen los tipos de material en los reportes.
    _REPORT_TIPO_ORDER = ('placa', 'formato', 'pieza')

    def _hold_line_is_backorder(self, line):
        """Material sin existencia por pedir.

        Una línea es "material sin existencia / por pedir" cuando es un producto
        físico (no servicio), sin placas ni quant asignados, pero con cantidad
        capturada manualmente desde el carrito (módulo inventory_shopping_cart).
        Replica la lógica de `_hold_line_is_backorder` de ese módulo para que los
        reportes la reconozcan aunque el carrito no esté instalado.
        """
        if not line.product_id or line.product_id.type == 'service':
            return False
        if line.lot_ids or line.lot_id or line.quant_id:
            return False
        return (line.cantidad_m2 or 0.0) > 0

    def _report_line_tipo(self, line):
        """Tipo (placa/formato/pieza) de una línea de material, tomado de sus placas."""
        lot = line.lot_ids[:1] or line.lot_id
        return lot.x_tipo or False

    def get_report_sections(self):
        """Estructura agrupada para los reportes de apartado.

        Separa las líneas en tres bloques y agrupa los materiales en existencia
        por tipo (Placa / Formato / Pieza) y, dentro de cada tipo, por línea de
        producto.

        Returns:
            dict: {
                'material_groups': [
                    {
                        'tipo_key': 'placa',
                        'tipo_label': 'Placa',
                        'lines': stock.lot.hold.order.line (recordset),
                        'placas': int,
                        'm2': float,
                        'subtotal': float,
                    }, ...
                ],
                'services':  stock.lot.hold.order.line (recordset),
                'backorder': stock.lot.hold.order.line (recordset),
            }
        """
        self.ensure_one()
        tipo_labels = dict(self.env['stock.lot']._fields['x_tipo'].selection)
        empty = self.env['stock.lot.hold.order.line']

        services = self.hold_line_ids.filtered(lambda l: l.product_id.type == 'service')
        backorder = self.hold_line_ids.filtered(self._hold_line_is_backorder)
        materials = self.hold_line_ids - services - backorder

        groups = {}
        for line in materials:
            key = self._report_line_tipo(line) or '_none'
            group = groups.get(key)
            if not group:
                group = {
                    'tipo_key': key,
                    'tipo_label': tipo_labels.get(key) or 'Sin Clasificar',
                    'lines': empty,
                    'placas': 0,
                    'm2': 0.0,
                    'subtotal': 0.0,
                }
                groups[key] = group

            group['lines'] |= line
            group['placas'] += len(line.lot_ids)
            group['m2'] += line.cantidad_m2 or 0.0
            group['subtotal'] += line.precio_total or 0.0

        order_index = {key: idx for idx, key in enumerate(self._REPORT_TIPO_ORDER)}
        material_groups = sorted(
            groups.values(),
            key=lambda g: (order_index.get(g['tipo_key'], 99), g['tipo_label']),
        )

        return {
            'material_groups': material_groups,
            'services': services,
            'backorder': backorder,
        }

    @api.model
    def _migrate_legacy_lines(self):
        """
        Consolida líneas legacy (lot_id Many2one, 1 línea = 1 lote)
        en líneas agrupadas por producto (lot_ids Many2many, 1 línea = N lotes).

        Seguro para ejecutar múltiples veces (idempotente).
        """
        orders = self.search([])
        migrated_count = 0

        for order in orders:
            lines_to_migrate = order.hold_line_ids.filtered(
                lambda l: l.lot_id and not l.lot_ids and l.product_id.type != 'service'
            )
            if not lines_to_migrate:
                continue

            product_groups = {}
            for line in lines_to_migrate:
                pid = line.product_id.id
                if pid not in product_groups:
                    product_groups[pid] = {
                        'lines': self.env['stock.lot.hold.order.line'],
                        'lot_ids': [],
                        'hold_ids': [],
                        'total_m2': 0.0,
                        'precio_unitario': 0.0,
                    }

                product_groups[pid]['lines'] |= line
                product_groups[pid]['lot_ids'].append(line.lot_id.id)

                if line.hold_id:
                    product_groups[pid]['hold_ids'].append(line.hold_id.id)

                product_groups[pid]['total_m2'] += line.cantidad_m2
                if line.precio_unitario:
                    product_groups[pid]['precio_unitario'] = line.precio_unitario

            for pid, group in product_groups.items():
                if len(group['lines']) <= 1:
                    line = group['lines'][0]
                    vals = {'lot_ids': [(6, 0, group['lot_ids'])]}
                    if group['hold_ids']:
                        vals['hold_ids'] = [(6, 0, group['hold_ids'])]
                    line.write(vals)
                else:
                    keeper = group['lines'][0]
                    to_delete = group['lines'] - keeper

                    vals = {
                        'lot_ids': [(6, 0, group['lot_ids'])],
                        'cantidad_m2': group['total_m2'],
                        'precio_unitario': group['precio_unitario'],
                    }
                    if group['hold_ids']:
                        vals['hold_ids'] = [(6, 0, group['hold_ids'])]
                    keeper.write(vals)

                    to_delete.unlink()
                    _logger.info(
                        "Migración: Orden %s, producto %s: consolidadas %d líneas → 1",
                        order.name,
                        pid,
                        len(group['lines']),
                    )

                migrated_count += 1

        _logger.info("Migración completada: %d órdenes procesadas", migrated_count)
        return migrated_count


class StockLotHoldOrderLine(models.Model):
    _name = 'stock.lot.hold.order.line'
    _description = 'Línea de Orden de Reserva'
    _order = 'id'

    order_id = fields.Many2one(
        'stock.lot.hold.order',
        string='Orden',
        required=True,
        ondelete='cascade',
    )
    product_id = fields.Many2one('product.product', string='Producto', required=True)

    # MÁSCARA COMERCIAL por venta (ver sale.order.line.x_mask_name): el
    # nombre con el que el cliente conoce el material en ESTA operación. Los
    # reportes del hold la imprimen en lugar del nombre real y al convertir
    # la reserva en orden de venta viaja a la línea de la SO.
    x_mask_name = fields.Char(
        string='Máscara',
        copy=True,
        help='Nombre comercial del material para ESTA venta. Los documentos '
             'imprimen la máscara en lugar del nombre real del producto y '
             'se propaga al convertir la reserva en orden de venta.',
    )

    # Campo principal: múltiples lotes por línea
    lot_ids = fields.Many2many(
        'stock.lot',
        'hold_order_line_lot_rel',
        'line_id',
        'lot_id',
        string='Placas Seleccionadas',
        domain="[('product_id', '=', product_id)]",
    )

    lot_count = fields.Integer(string='# Placas', compute='_compute_lot_count', store=True)

    # Campos legacy
    lot_id = fields.Many2one('stock.lot', string='Lote (legacy)', required=False)
    quant_id = fields.Many2one('stock.quant', string='Quant', required=False, ondelete='set null', index=True)

    cantidad_m2 = fields.Float(
        string='Cantidad (m²)',
        store=True,
        readonly=False,
        compute='_compute_cantidad_m2',
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Moneda',
        related='order_id.currency_id',
        store=True,
        readonly=True,
    )
    precio_unitario = fields.Monetary(string='Precio/m²', currency_field='currency_id')
    precio_total = fields.Monetary(
        string='Total',
        compute='_compute_precio_total',
        store=True,
        currency_field='currency_id',
    )

    hold_ids = fields.Many2many(
        'stock.lot.hold',
        'hold_order_line_hold_rel',
        'line_id',
        'hold_id',
        string='Holds Creados',
        readonly=True,
    )
    hold_id = fields.Many2one('stock.lot.hold', string='Hold (legacy)', readonly=True)

    # Related del primer lote para compatibilidad legacy
    x_color = fields.Char(related='lot_id.x_color', string='Color', readonly=True)
    x_grosor = fields.Char(related='lot_id.x_grosor', string='Grosor (cm)', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', string='Alto (m)', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', string='Largo (m)', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', string='Bloque', readonly=True)
    x_tipo = fields.Selection(related='lot_id.x_tipo', string='Tipo', readonly=True)

    @api.depends('lot_ids')
    def _compute_lot_count(self):
        for line in self:
            line.lot_count = len(line.lot_ids)

    def write(self, vals):
        res = super().write(vals)
        if 'lot_ids' in vals:
            self._sync_holds_with_lots()
        return res

    def unlink(self):
        # Al borrar una línea se liberan sus apartados activos. Sin esto los
        # holds quedaban huérfanos (activos pero ya sin línea que los apunte):
        # la placa se quedaba bloqueada para siempre y ni cancelar la orden
        # la liberaba, porque la liberación recorre las líneas.
        self._release_active_holds()
        return super().unlink()

    def _release_active_holds(self, only_lots=None):
        """Cancela los holds ACTIVOS de la línea (todos, o solo los de
        `only_lots`) y lo deja asentado en el chatter de la orden."""
        for line in self:
            holds = line.hold_ids.filtered(lambda h: h.estado == 'activo')
            if only_lots is not None:
                holds = holds.filtered(lambda h: h.lot_id in only_lots)
            if not holds:
                continue
            lot_names = ', '.join(holds.mapped('lot_id.name'))
            holds.write({'estado': 'cancelado'})
            if line.order_id:
                line.order_id.message_post(body=(
                    f'Se liberaron {len(holds)} apartado(s) al quitar placas '
                    f'de la reserva: {lot_names}.'
                ))

    def _sync_holds_with_lots(self):
        """Mantiene el invariante «placas de la línea ⇔ holds activos».

        - Placa quitada: su hold activo se cancela al momento (la placa vuelve
          a estar disponible en carrito/apartados).
        - Placa agregada con la orden CONFIRMADA: se crea su hold de inmediato,
          con las mismas validaciones que la confirmación (si la placa ya está
          apartada por otro documento, el cambio truena y no se guarda a medias).
        """
        for line in self:
            active = line.hold_ids.filtered(lambda h: h.estado == 'activo')
            stale = active.filtered(lambda h: h.lot_id not in line.lot_ids)
            if stale:
                line._release_active_holds(only_lots=stale.mapped('lot_id'))

            order = line.order_id
            if (
                order
                and order.state == 'confirmed'
                and line.product_id
                and line.product_id.type != 'service'
            ):
                held_lots = (active - stale).mapped('lot_id')
                for lot in (line.lot_ids - held_lots):
                    order._create_hold_for_line_lot(line, lot)

    def _som_lot_free_qty(self, lot):
        """m² LIBRES del lote: físico interno menos lo ya asignado.

        'Asignado' cubre las dos rutas reales:
        - reserved_quantity del quant (reservas estándar de inventario), y
        - move lines VIVAS ligadas a una venta confirmada (la asignación
          para entrega de una SO que crea el wizard, que no siempre
          reserva el quant).
        Se toma el MÁXIMO de ambas para no restar doble cuando la reserva
        estándar sí existe. El apartado jamás propone ni acepta material
        que otro documento ya comprometió."""
        quants = self.env['stock.quant'].sudo().search([
            ('lot_id', '=', lot.id),
            ('quantity', '>', 0),
            ('location_id.usage', '=', 'internal'),
        ])
        fisico = sum(quants.mapped('quantity'))
        reservado = sum(quants.mapped('reserved_quantity'))

        Ml = self.env['stock.move.line'].sudo()
        qty_field = 'quantity' if 'quantity' in Ml._fields else 'qty_done'
        mls = Ml.search([
            ('lot_id', '=', lot.id),
            ('state', 'not in', ('done', 'cancel')),
            ('move_id.sale_line_id', '!=', False),
            ('move_id.sale_line_id.order_id.state', 'in', ('sale', 'done')),
        ])
        asignado_so = sum(mls.mapped(qty_field))

        # Asignación CAPTURADA en órdenes/cotizaciones vivas (lot_ids +
        # desglose de parcialidades): existe antes de cualquier move line
        # y también debe respetarla el apartado. Sin esto, con material
        # seleccionado en un pedido el hold aceptaba el lote completo.
        asignado_sol = 0.0
        Sol = self.env['sale.order.line'].sudo()
        if 'lot_ids' in Sol._fields:
            sols = Sol.search([
                ('lot_ids', 'in', lot.id),
                ('order_id.state', 'in', ('draft', 'sent', 'sale')),
            ])
            for sol in sols:
                qty = None
                if hasattr(sol, '_som_breakdown_qty_for_lot'):
                    bd = getattr(sol, 'x_lot_breakdown_json', None)
                    if bd:
                        qty = sol._som_breakdown_qty_for_lot(bd, lot)
                if qty is None:
                    # Sin desglose = lote tomado completo (placas).
                    qty = fisico
                asignado_sol += float(qty or 0.0)

        # Retenido por holds ACTIVOS de otras órdenes de reserva (el
        # apartado parcial solo retiene su parcialidad; placas completas).
        own_hold_ids = set()
        if self and 'hold_ids' in self._fields:
            own_hold_ids = set(self.hold_ids.ids)
        retenido = 0.0
        for q in quants:
            h = getattr(q, 'x_hold_activo_id', False)
            if not h or h.id in own_hold_ids:
                continue
            retenido += q.som_hold_held_qty()

        asignado = max(reservado, asignado_so, min(asignado_sol, fisico))
        return fisico, asignado, max(fisico - asignado - retenido, 0.0)

    @api.depends('lot_ids', 'product_id')
    def _compute_cantidad_m2(self):
        for line in self:
            if line.lot_ids:
                total = 0.0
                for lot in line.lot_ids:
                    # Solo lo LIBRE del lote: el físico total incluía m² ya
                    # asignados a pedidos y sembraba sobre-asignación.
                    total += line._som_lot_free_qty(lot)[2]
                line.cantidad_m2 = total
            elif line.product_id and line.product_id.type == 'service':
                if not line.cantidad_m2:
                    line.cantidad_m2 = 1.0
            else:
                line.cantidad_m2 = 0.0

    @api.constrains('cantidad_m2', 'lot_ids', 'product_id')
    def _check_cantidad_vs_libre(self):
        """La cantidad manual del apartado no puede superar lo LIBRE de
        sus lotes (físico interno − asignado a pedidos/entregas). Antes se
        podía teclear cualquier cantidad y, con parte del lote ya asignada
        a una orden, el hold rebasaba el material real."""
        for line in self:
            if not line.lot_ids or not line.product_id \
                    or line.product_id.type == 'service':
                continue
            total_libre = 0.0
            detalle = []
            for lot in line.lot_ids:
                fisico, asignado, libre = line._som_lot_free_qty(lot)
                total_libre += libre
                detalle.append(
                    '%s: %.2f libres (físico %.2f − asignado %.2f)'
                    % (lot.name, libre, fisico, asignado))
            if float_compare(line.cantidad_m2 or 0.0, total_libre,
                             precision_digits=2) > 0:
                raise ValidationError(_(
                    'La cantidad del apartado (%(qty).2f m²) supera el '
                    'material LIBRE de sus lotes (%(free).2f m²).\n\n'
                    'Detalle por lote:\n%(det)s\n\n'
                    'El material asignado a pedidos o entregas no puede '
                    'apartarse de nuevo.',
                    qty=line.cantidad_m2, free=total_libre,
                    det='\n'.join(detalle)))

    @api.depends('cantidad_m2', 'precio_unitario')
    def _compute_precio_total(self):
        for line in self:
            line.precio_total = (line.cantidad_m2 or 0.0) * (line.precio_unitario or 0.0)

    @api.onchange('lot_ids')
    def _onchange_lot_ids(self):
        if self.lot_ids:
            self.lot_id = self.lot_ids[0]

            if not self.product_id:
                self.product_id = self.lot_ids[0].product_id

            quant = self.env['stock.quant'].search([
                ('lot_id', '=', self.lot_ids[0].id),
                ('quantity', '>', 0),
                ('location_id.usage', '=', 'internal'),
            ], limit=1)
            self.quant_id = quant.id if quant else False

            # Refrescar valores visuales en formulario (TODOS los quants
            # internos de cada lote, igual que el cómputo almacenado)
            total = 0.0
            for lot in self.lot_ids:
                quants_line = self.env['stock.quant'].search([
                    ('lot_id', '=', lot.id),
                    ('quantity', '>', 0),
                    ('location_id.usage', '=', 'internal'),
                ])
                total += sum(quants_line.mapped('quantity'))
            self.cantidad_m2 = total
        else:
            self.lot_id = False
            self.quant_id = False
            if not (self.product_id and self.product_id.type == 'service'):
                self.cantidad_m2 = 0.0

    @api.onchange('product_id')
    def _onchange_product_id(self):
        if self.product_id and self.product_id.type == 'service':
            self.lot_ids = [(5, 0, 0)]
            self.lot_id = False
            self.quant_id = False
            if not self.cantidad_m2:
                self.cantidad_m2 = 1.0