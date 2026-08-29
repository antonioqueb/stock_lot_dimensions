# -*- coding: utf-8 -*-
# models/stock_lot_hold_order.py
from markupsafe import Markup, escape

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_amount
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

    # Contacto a la vista, igual que en la orden de venta: el correo del
    # apartado es el que recibe la confirmación y los avisos de
    # vencimiento, así que tiene que verse (y poder corregirse) aquí
    # mismo. `related` editable: lo capturado se guarda en la ficha del
    # cliente. Odoo 19: res.partner ya no tiene `mobile`.
    x_partner_email = fields.Char(
        related='partner_id.email',
        string='Correo del cliente',
        readonly=False,
    )
    x_partner_phone = fields.Char(
        related='partner_id.phone',
        string='Teléfono del cliente',
        readonly=False,
    )

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
    # Estatus de negocio para la lista/filtros: VIGENTE, VENCIDA,
    # CANCELADA o EN SO (más borrador/finalizada). Almacenado para poder
    # agrupar; sus dependencias son campos stored (la bandera de
    # vencimiento la mantiene el cron horario).
    x_estatus_reserva = fields.Selection([
        ('borrador', 'Borrador'),
        ('vigente', 'Vigente'),
        ('vencida', 'Vencida'),
        ('en_so', 'En SO'),
        ('finalizada', 'Finalizada'),
        ('cancelada', 'Cancelada'),
    ], string='Estatus', compute='_compute_x_estatus_reserva', store=True)

    @api.depends('state', 'x_expired_flag', 'sale_order_id')
    def _compute_x_estatus_reserva(self):
        for order in self:
            if order.state == 'cancel':
                order.x_estatus_reserva = 'cancelada'
            elif order.sale_order_id:
                order.x_estatus_reserva = 'en_so'
            elif order.state == 'done':
                order.x_estatus_reserva = 'finalizada'
            elif order.state == 'confirmed':
                order.x_estatus_reserva = (
                    'vencida' if order.x_expired_flag else 'vigente')
            else:
                order.x_estatus_reserva = 'borrador'

    x_expiry_seller_notified = fields.Boolean(
        copy=False, help='Ya se avisó al vendedor del vencimiento.')
    x_client_expiry_notice_sent = fields.Boolean(
        copy=False, help='Ya se envió al cliente el aviso de que su reserva '
        'vence en 1 día.')
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
                        '⚠ RESERVA VENCIDA (1ª vez). Las placas quedaron '
                        'LIBERADAS al inventario (la fecha manda), pero se '
                        'conservan en esta orden: Renovar las re-aparta si '
                        'siguen libres. Al SEGUNDO vencimiento el material '
                        'se eliminará automáticamente de la reserva.'))

            if order.x_expired_count <= 1:
                # Primer vencimiento: las LÍNEAS se conservan en la orden,
                # pero los holds SÍ expiran — vencido = placa libre, sí o
                # sí. (Antes se mantenían activos y el material seguía
                # bloqueado para todos, contra la regla de negocio.)
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
                # Hora de Monterrey (add_business_days a pelo contaba en UTC:
                # viernes/fin de semana por la noche perdía un día hábil).
                vals['fecha_expiracion'] = BusinessDaysCalculator.get_expiration_date(fecha_base, 5)

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

            # CONFIRMAR NO MANDA CORREO (pedido del 15 ago 2026). El correo
            # de la reserva sale ÚNICAMENTE por el botón "Enviar Correo",
            # que abre el compositor con preview y destinatario editable.
            order.message_post(body=Markup(
                'Reserva confirmada (vence el %s). El correo al cliente no '
                'se envía solo: usa el botón <b>Enviar Correo</b>.'
            ) % order._som_expiry_local_str())

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
            # Renovar re-arma los avisos: el próximo vencimiento vuelve a
            # notificar al vendedor y el T-1 al cliente.
            order.x_expiry_seller_notified = False
            order.x_client_expiry_notice_sent = False
            order.message_post(body=(
                f'Reserva renovada hasta {som_format_date(nueva_expiracion, with_time=True)}: '
                f'{len(active_holds)} hold(s) extendido(s)'
                + (f', {len(expired_holds)} reactivado(s).' if expired_holds else '.')
            ))

    # ------------------------------------------------------------------
    #  AVISOS DE VENCIMIENTO
    # ------------------------------------------------------------------
    def _som_expiry_local_str(self):
        self.ensure_one()
        import pytz
        if not self.fecha_expiracion:
            return ''
        local = pytz.utc.localize(self.fecha_expiracion).astimezone(
            pytz.timezone('America/Monterrey'))
        return som_format_date(local, with_time=True)

    def _som_expiry_local_str_en(self):
        """Vencimiento en hora de Monterrey con formato inglés (para el
        correo de confirmación al cliente, que va en inglés)."""
        self.ensure_one()
        import pytz
        if not self.fecha_expiracion:
            return ''
        local = pytz.utc.localize(self.fecha_expiracion).astimezone(
            pytz.timezone('America/Monterrey'))
        return local.strftime('%b %d, %Y · %I:%M %p')

    def _som_hold_lines_html(self, lang='es'):
        """Panel de material reservado para los correos: cada producto con
        sus placas (lote, bloque, alto × ancho y m²) y totales al pie."""
        self.ensure_one()
        L = {
            'es': {'header': 'Material reservado', 'slabs': 'placa(s)',
                   'block': 'Bloque'},
            'en': {'header': 'Reserved material', 'slabs': 'slab(s)',
                   'block': 'Block'},
        }.get(lang) or {'header': 'Material reservado',
                        'slabs': 'placa(s)', 'block': 'Bloque'}
        blocks = []
        total_placas = 0
        total_m2 = 0.0
        for line in self.hold_line_ids:
            if line.product_id.type == 'service':
                continue
            lot_rows = []
            for lot in line.lot_ids:
                dims = ''
                if lot.x_alto and lot.x_ancho:
                    dims = '%.2f × %.2f m · %.2f m²' % (
                        lot.x_alto, lot.x_ancho, lot.x_alto * lot.x_ancho)
                lot_rows.append(
                    '<tr>'
                    '<td style="padding:2px 0;font-size:12px;'
                    'color:#3D352C;">%s%s</td>'
                    '<td style="padding:2px 0 2px 10px;text-align:right;'
                    'font-size:12px;color:#8A8072;">'
                    '%s</td></tr>' % (
                        lot.name or '',
                        (' · %s %s' % (L['block'], lot.x_bloque))
                        if lot.x_bloque else '',
                        dims))
            total_placas += len(line.lot_ids)
            total_m2 += line.cantidad_m2 or 0.0
            blocks.append(
                '<div style="margin:0 0 12px;">'
                '<div style="font-size:13px;border-bottom:1px solid '
                '#D8D2C6;padding-bottom:3px;">'
                '<b style="color:#2C221B;">%s</b>'
                '<span style="color:#8A8072;"> — %s %s · '
                '%.2f m²</span></div>'
                '<table role="presentation" width="100%%" cellpadding="0" '
                'cellspacing="0" style="margin-top:4px;">%s</table>'
                '</div>' % (
                    line.x_mask_name or line.product_id.display_name,
                    len(line.lot_ids),
                    L['slabs'],
                    line.cantidad_m2 or 0.0,
                    ''.join(lot_rows)))
        if not blocks:
            return ''
        return (
            '<div style="background:#ECE9E1;padding:14px 18px 10px;'
            'margin:0 0 14px;">'
            '<div style="font-size:10px;letter-spacing:.2em;'
            'text-transform:uppercase;color:#8A8072;margin-bottom:10px;">'
            '%s</div>'
            '%s'
            '<div style="font-size:12px;font-weight:700;color:#2C221B;'
            'border-top:1px solid #2C221B;padding-top:6px;'
            'text-align:right;">Total: %s %s · %.2f m²</div>'
            '</div>'
        ) % (L['header'], ''.join(blocks), total_placas, L['slabs'],
             total_m2)

    def _som_branded_mail_html(self, kicker, title, subtitle, inner_html):
        """Envuelve el contenido en la plantilla de correo (SOM) del manual
        de identidad: White Coffee #E2DED5, Raisin Black #2C221B, grotesca
        con tracking amplio y etiquetas entre paréntesis (eco del wordmark).
        Mismo esqueleto que confirmación/cotización/OC."""
        self.ensure_one()
        company = self.company_id or self.env.company
        contact_bits = [company.name or 'SOM Group']
        if company.phone:
            contact_bits.append(company.phone)
        if company.email:
            contact_bits.append(company.email)
        return (
            '<div style="margin:0;padding:16px 8px;background-color:#E2DED5;'
            "font-family:'Anderson Grotesk','Helvetica Neue',Helvetica,Arial,"
            'sans-serif;">'
            '<table role="presentation" width="100%%" cellpadding="0" '
            'cellspacing="0" style="max-width:600px;margin:0 auto;'
            'background:#ffffff;">'
            '<tr><td style="height:4px;background:#2C221B;font-size:0;'
            'line-height:0;">&#160;</td></tr>'
            '<tr><td style="padding:22px 28px 0;">'
            '<table role="presentation" width="100%%" cellpadding="0" '
            'cellspacing="0"><tr>'
            '<td style="vertical-align:middle;">'
            '<img src="%(base)s/theme_list_modern/static/img/logosom.png" '
            'alt="(SOM)" style="height:28px;width:auto;display:block;"/></td>'
            '<td style="vertical-align:middle;text-align:right;font-size:9px;'
            'letter-spacing:.24em;text-transform:uppercase;color:#8A8072;'
            'white-space:nowrap;">%(kicker)s</td>'
            '</tr></table>'
            '<div style="margin-top:16px;border-top:1px solid #2C221B;"></div>'
            '</td></tr>'
            '<tr><td style="padding:18px 28px 0;">'
            '<div style="font-size:24px;font-weight:300;letter-spacing:.01em;'
            'color:#2C221B;line-height:1.25;">%(title)s</div>'
            '<div style="font-size:10px;letter-spacing:.16em;'
            'text-transform:uppercase;color:#8A8072;margin-top:8px;'
            'line-height:1.7;">%(subtitle)s</div>'
            '</td></tr>'
            '<tr><td style="padding:16px 28px 24px;font-size:14px;'
            'color:#3D352C;line-height:1.7;">%(inner)s</td></tr>'
            '<tr><td style="padding:20px 28px;background:#2C221B;'
            'text-align:center;">'
            '<div style="font-size:13px;letter-spacing:.3em;color:#E2DED5;">'
            '(SOM)<span style="font-size:8px;vertical-align:super;">&#174;'
            '</span></div>'
            '<div style="font-size:8px;letter-spacing:.26em;'
            'text-transform:uppercase;color:#A79C8C;font-style:italic;'
            'margin-top:5px;">Recubrimientos &#218;nicos</div>'
            '<div style="font-size:9px;letter-spacing:.14em;'
            'text-transform:uppercase;color:#A79C8C;margin-top:12px;'
            'line-height:1.9;">%(contact)s</div>'
            '</td></tr>'
            '</table></div>'
        ) % {
            'base': self.get_base_url(),
            'kicker': kicker,
            'title': title,
            'subtitle': subtitle,
            'inner': inner_html,
            'contact': '<br/>'.join(contact_bits),
        }

    def _som_send_plain_mail(self, email_to, subject, body_html):
        if not email_to:
            return False
        try:
            self.env['mail.mail'].sudo().create({
                'subject': subject,
                'body_html': body_html,
                'email_to': email_to,
                'email_from': (
                    self.company_id.email
                    or self.env.company.email or False),
                'auto_delete': True,
            }).send()
            return True
        except Exception:
            _logger.exception(
                '[HOLD NOTIFY] No se pudo enviar el correo "%s" a %s.',
                subject, email_to)
            return False

    def _som_notify_seller_expired(self):
        """Reserva VENCIDA: aviso al VENDEDOR por Odoo (actividad) y por
        correo. Lo dispara el cron al primer vencimiento."""
        for order in self:
            if order.x_expiry_seller_notified or not order.user_id:
                continue
            seller = order.user_id
            detalle = order._som_hold_lines_html()
            try:
                order.activity_schedule(
                    'mail.mail_activity_data_todo',
                    summary='Reserva VENCIDA: %s (%s)' % (
                        order.name, order.partner_id.display_name or ''),
                    note=(
                        '<p><b>⏰ La reserva %s venció</b> (%s).</p>'
                        '<p>Las placas quedaron LIBERADAS al inventario, '
                        'pero se conservan en la orden: <b>Renovar</b> las '
                        're-aparta si siguen libres. Al segundo vencimiento '
                        'el material se eliminará de la reserva.</p>%s'
                    ) % (order.name, order._som_expiry_local_str(), detalle),
                    user_id=seller.id,
                )
            except Exception:
                _logger.exception(
                    '[HOLD NOTIFY] Sin actividad de vencimiento para %s.',
                    order.name)
            order._som_send_plain_mail(
                seller.email,
                'Reserva vencida %s · %s' % (
                    order.name, order.partner_id.display_name or ''),
                order._som_branded_mail_html(
                    kicker='Aviso interno',
                    title='La reserva ha vencido.',
                    subtitle='%s &#183; venci&#243; el %s &#183; '
                             'hora de Monterrey' % (
                        order.name, order._som_expiry_local_str()),
                    inner_html=(
                        '<p style="margin:0 0 14px;">Hola %s,</p>'
                        '<p style="margin:0 0 14px;">La reserva <b>%s</b> de '
                        '<b>%s</b> venció y las placas quedaron '
                        '<b>liberadas al inventario</b>, aunque siguen '
                        'listadas en la orden.</p>'
                        '<p style="margin:0 0 14px;">Si el cliente continúa '
                        'interesado, <b>renuévala cuanto antes</b> — otro '
                        'vendedor puede tomarlas en cualquier momento. Al '
                        'segundo vencimiento el material se eliminará de la '
                        'reserva.</p>%s'
                    ) % (
                        seller.name, order.name,
                        order.partner_id.display_name or '',
                        order._som_hold_lines_html(),
                    )))
            order.x_expiry_seller_notified = True

    def _som_notify_client_expiry_tomorrow(self):
        """T-1: correo al CLIENTE con sesgo de escasez — su reserva vence
        mañana y el material único se libera para cualquier otro."""
        for order in self:
            if order.x_client_expiry_notice_sent:
                continue
            email = order.partner_id.email
            if not email:
                order.x_client_expiry_notice_sent = True
                order.message_post(body=(
                    '⏳ Aviso T-1 al cliente OMITIDO: el contacto no tiene '
                    'correo registrado.'))
                continue
            seller = order.user_id
            contacto = ''
            if seller:
                contacto = (
                    '<p>Para extender tu reserva o confirmar tu pedido, '
                    'responde este correo o contacta a <b>%s</b>%s.</p>'
                ) % (
                    seller.name,
                    (' (%s)' % seller.email) if seller.email else '',
                )
            ok = order._som_send_plain_mail(
                email,
                'Tu reserva %s vence mañana — el material se liberará' % (
                    order.name),
                order._som_branded_mail_html(
                    kicker='Aviso de vencimiento',
                    title='Tu reserva vence ma&#241;ana.',
                    subtitle='%s &#183; vence el %s &#183; '
                             'hora de Monterrey' % (
                        order.name, order._som_expiry_local_str()),
                    inner_html=(
                        '<p style="margin:0 0 14px;">Estimado(a) '
                        '<b>%s</b>,</p>'
                        '<p style="margin:0 0 14px;">Tu reserva <b>%s</b> '
                        'está por vencer.</p>'
                        '%s'
                        '<p style="margin:0 0 14px;"><b>Importante:</b> '
                        'buena parte de nuestro material se compone de '
                        'piezas únicas — en la piedra natural, cada bloque '
                        'tiene vetas y tonos que no vuelven a repetirse. Al '
                        'vencer tu reserva, este material queda '
                        '<b>disponible de inmediato para cualquier otro '
                        'cliente</b> y no podemos garantizar que encuentres '
                        'piezas equivalentes después.</p>'
                        '%s'
                        '<p style="margin:22px 0 0;font-style:italic;'
                        'color:#2C221B;">No solo cubrimos superficies — '
                        'creamos espacios que inspiran.</p>'
                        '<p style="margin:14px 0 0;font-size:13px;">Saludos,'
                        '<br/><span style="font-weight:600;">%s</span></p>'
                    ) % (
                        order.partner_id.name or '',
                        order.name,
                        order._som_hold_lines_html(),
                        contacto,
                        order.company_id.name or 'SOM Group',
                    )))
            if ok:
                order.x_client_expiry_notice_sent = True
                order.message_post(body=(
                    '⏳ Aviso de vencimiento T-1 enviado al cliente (%s).'
                ) % email)

    def _som_hold_lines_markup(self):
        """Panel de material como Markup para t-out en el mail template
        de confirmación. Sin Markup, QWeb escaparía el HTML."""
        self.ensure_one()
        return Markup(self._som_hold_lines_html())

    # ------------------------------------------------------------------
    #  RESUMEN CON PRECIOS (correo de reserva)
    # ------------------------------------------------------------------
    SOM_HOLD_TAX_RATE = 0.16

    def _som_hold_summary_html(self, lang='es'):
        """RESUMEN de la reserva para el correo: una fila por línea con el
        precio colocado y el importe, más subtotal, IVA y total.

        A propósito NO desglosa placa por placa (eso vive en el PDF de
        detalle que viaja adjunto): el correo es el resumen comercial.
        """
        self.ensure_one()
        L = {
            'es': {'header': 'Resumen de tu reserva', 'concept': 'Concepto',
                   'qty': 'Cantidad', 'unit': 'Precio unitario',
                   'amount': 'Importe', 'subtotal': 'Subtotal',
                   'tax': 'IVA 16%', 'total': 'Total',
                   'slabs': 'placa(s)', 'service': 'Servicio'},
            'en': {'header': 'Reservation summary', 'concept': 'Item',
                   'qty': 'Quantity', 'unit': 'Unit price',
                   'amount': 'Amount', 'subtotal': 'Subtotal',
                   'tax': 'VAT 16%', 'total': 'Total',
                   'slabs': 'slab(s)', 'service': 'Service'},
        }.get(lang) or {}
        L = L or {'header': 'Resumen de tu reserva', 'concept': 'Concepto',
                  'qty': 'Cantidad', 'unit': 'Precio unitario',
                  'amount': 'Importe', 'subtotal': 'Subtotal',
                  'tax': 'IVA 16%', 'total': 'Total',
                  'slabs': 'placa(s)', 'service': 'Servicio'}

        currency = self.currency_id or self.company_id.currency_id
        money = lambda amount: format_amount(  # noqa: E731
            self.env, amount or 0.0, currency)

        rows = []
        for line in self.hold_line_ids:
            is_service = line.product_id.type == 'service'
            qty = line.cantidad_m2 or 0.0
            if is_service:
                qty_txt = L['service']
            else:
                qty_txt = '%.2f m²' % qty
                if line.lot_ids:
                    qty_txt += ' · %d %s' % (len(line.lot_ids), L['slabs'])
            rows.append(
                '<tr>'
                '<td style="padding:7px 0;font-size:13px;color:#2C221B;'
                'border-bottom:1px solid #D8D2C6;">%s'
                '<div style="font-size:11px;color:#8A8072;margin-top:2px;">'
                '%s</div></td>'
                '<td style="padding:7px 0 7px 10px;text-align:right;'
                'font-size:12px;color:#8A8072;white-space:nowrap;'
                'border-bottom:1px solid #D8D2C6;">%s</td>'
                '<td style="padding:7px 0 7px 10px;text-align:right;'
                'font-size:13px;color:#2C221B;white-space:nowrap;'
                'border-bottom:1px solid #D8D2C6;">%s</td>'
                '</tr>' % (
                    escape(line.x_mask_name
                           or line.product_id.display_name or ''),
                    qty_txt,
                    money(line.precio_unitario),
                    money(line.precio_total)))

        if not rows:
            return ''

        subtotal = self.total_con_precio or 0.0
        tax = subtotal * self.SOM_HOLD_TAX_RATE
        total = subtotal + tax

        def totals_row(label, value, strong=False):
            weight = '700' if strong else '400'
            return (
                '<tr>'
                '<td style="padding:4px 0;font-size:12px;color:#3D352C;'
                'font-weight:%s;">%s</td>'
                '<td style="padding:4px 0 4px 10px;text-align:right;'
                'font-size:12px;color:#2C221B;font-weight:%s;'
                'white-space:nowrap;">%s</td>'
                '</tr>' % (weight, label, weight, value))

        return (
            '<div style="background:#ECE9E1;padding:14px 18px;margin:0 0 14px;">'
            '<div style="font-size:10px;letter-spacing:.2em;'
            'text-transform:uppercase;color:#8A8072;margin-bottom:10px;">'
            '%s</div>'
            '<table role="presentation" width="100%%" cellpadding="0" '
            'cellspacing="0">'
            '<tr>'
            '<td style="padding:0 0 6px;font-size:9px;letter-spacing:.16em;'
            'text-transform:uppercase;color:#8A8072;">%s</td>'
            '<td style="padding:0 0 6px 10px;text-align:right;font-size:9px;'
            'letter-spacing:.16em;text-transform:uppercase;color:#8A8072;'
            'white-space:nowrap;">%s</td>'
            '<td style="padding:0 0 6px 10px;text-align:right;font-size:9px;'
            'letter-spacing:.16em;text-transform:uppercase;color:#8A8072;'
            'white-space:nowrap;">%s</td>'
            '</tr>'
            '%s'
            '</table>'
            '<table role="presentation" width="100%%" cellpadding="0" '
            'cellspacing="0" style="margin-top:10px;">'
            '%s%s'
            '<tr><td colspan="2" style="padding:6px 0 0;'
            'border-top:1px solid #2C221B;"></td></tr>'
            '%s'
            '</table>'
            '</div>'
        ) % (
            L['header'], L['concept'], L['unit'], L['amount'],
            ''.join(rows),
            totals_row(L['subtotal'], money(subtotal)),
            totals_row(L['tax'], money(tax)),
            totals_row(L['total'], money(total), strong=True),
        )

    def _som_hold_summary_markup(self):
        """Resumen con precios como Markup para t-out en el mail template."""
        self.ensure_one()
        return Markup(self._som_hold_summary_html())

    def action_send_hold_confirmation_email(self):
        """Botón: abre el compositor de correo con el template de reserva
        confirmada precargado — preview editable y destinatario a elegir,
        igual que el envío por correo de la orden de venta."""
        self.ensure_one()
        if self.state != 'confirmed':
            raise UserError(
                'Solo se puede enviar el correo de una reserva confirmada.')
        template = self.env.ref(
            'stock_lot_dimensions.mail_template_hold_confirmed',
            raise_if_not_found=False)
        ctx = {
            'default_model': 'stock.lot.hold.order',
            'default_res_ids': self.ids,
            'default_composition_mode': 'comment',
            'default_template_id': template.id if template else False,
            'force_email': True,
        }
        return {
            'type': 'ir.actions.act_window',
            'name': 'Enviar correo de reserva',
            'res_model': 'mail.compose.message',
            'view_mode': 'form',
            'target': 'new',
            'context': ctx,
        }

    # NOTA: aquí vivía _som_notify_client_hold_confirmed(), el envío
    # automático al confirmar. Se eliminó el 15 ago 2026: confirmar NUNCA
    # manda correo; el único disparador es action_send_hold_confirmation_email
    # (botón Enviar Correo → compositor). Los avisos T-1/vencido siguen
    # siendo automáticos: esos sí son recordatorios, no la confirmación.

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

        # El guard es POR PLACA, no por registro de hold: la línea
        # acumula holds HISTÓRICOS (mover una placa de bin cancela el
        # hold viejo y crea uno nuevo activo). Basta un hold activo por
        # lote. Si alguna placa de verdad perdió su reserva (vencida,
        # cancelada o apartada por otro), NO se bloquea a ciegas: se
        # informa QUÉ placas son y el vendedor decide — convertir solo
        # con lo disponible (contexto hold_convert_drop_unavailable, lo
        # manda el wizard de confirmación) o actualizar su selección.
        drop_unavailable = self.env.context.get(
            'hold_convert_drop_unavailable')
        skip_line_ids = set()
        missing_report = []
        for line in self.hold_line_ids:
            if line.product_id.type == 'service':
                continue
            active_lot_ids = set(
                line.hold_ids.filtered(
                    lambda h: h.estado == 'activo').mapped('lot_id').ids)
            missing_lots = line.lot_ids.filtered(
                lambda l: l.id not in active_lot_ids)
            if not missing_lots:
                continue
            if not drop_unavailable:
                missing_report.append('%s: %s' % (
                    line.product_id.display_name,
                    ', '.join(missing_lots.mapped('name'))))
                continue
            # Poda autorizada: fuera las placas sin reserva, la línea
            # sigue con lo disponible (m² ajustados por dimensiones).
            keep = line.lot_ids - missing_lots
            dropped_area = sum(
                (l.x_alto or 0.0) * (l.x_ancho or 0.0)
                for l in missing_lots)
            vals = {'lot_ids': [(6, 0, keep.ids)]}
            if 'cantidad_m2' in line._fields and dropped_area:
                vals['cantidad_m2'] = max(
                    (line.cantidad_m2 or 0.0) - dropped_area, 0.0)
            line.with_context(skip_hold_validation=True).write(vals)
            self.message_post(body=(
                '✂️ Conversión parcial: se excluyeron placas SIN reserva '
                'activa de %s: %s (%.2f m²).' % (
                    line.product_id.display_name,
                    ', '.join(missing_lots.mapped('name')),
                    dropped_area)))
            if not keep:
                skip_line_ids.add(line.id)

        if missing_report:
            wiz = self.env['stock.lot.hold.convert.confirm'].create({
                'order_id': self.id,
                'detail': (
                    'Estas placas YA NO tienen una reserva activa '
                    '(vencida, cancelada o apartada/vendida por otro):\n\n'
                    + '\n'.join('• %s' % m for m in missing_report)),
            })
            return {
                'type': 'ir.actions.act_window',
                'name': 'Placas sin reserva activa',
                'res_model': 'stock.lot.hold.convert.confirm',
                'res_id': wiz.id,
                'view_mode': 'form',
                'target': 'new',
            }

        product_groups = {}
        services_list = []

        for line in self.hold_line_ids:
            if line.id in skip_line_ids:
                continue
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

    @api.model_create_multi
    def create(self, vals_list):
        """Línea NUEVA con placas en una reserva YA CONFIRMADA: aparta de
        inmediato (mismo invariante que write). Sin esto la línea se guardaba
        con placas anotadas pero sin hold formal, otra vendedora podía
        tomarlas y al convertir se excluían (caso RES/00328 → V/663, 28 ago
        2026). En órdenes en borrador no hace nada: los holds nacen al
        confirmar, como siempre."""
        lines = super().create(vals_list)
        to_sync = lines.filtered(
            lambda l: l.order_id and l.order_id.state == 'confirmed' and l.lot_ids)
        if to_sync:
            to_sync._sync_holds_with_lots()
        return lines

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

class StockLotHoldConvertConfirm(models.TransientModel):
    _name = 'stock.lot.hold.convert.confirm'
    _description = 'Confirmación: convertir hold con placas sin reserva'

    order_id = fields.Many2one(
        'stock.lot.hold.order', required=True, ondelete='cascade')
    detail = fields.Text(readonly=True)

    def action_convert_available(self):
        """Convertir SOLO con la selección disponible: poda las placas sin
        reserva activa y sigue con la conversión normal."""
        self.ensure_one()
        return self.order_id.with_context(
            hold_convert_drop_unavailable=True,
        ).action_convert_to_sale_order()

    def action_update_selection(self):
        """El vendedor prefiere depurar su selección a mano: se abre la
        orden de reserva y no se convierte nada."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold.order',
            'res_id': self.order_id.id,
            'view_mode': 'form',
            'target': 'current',
        }
