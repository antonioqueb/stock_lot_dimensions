# -*- coding: utf-8 -*-
# models/stock_move_line.py

import logging

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError

from .utils.lot_dimension_sync import LotDimensionSync
from .utils.notification_builder import NotificationBuilder
from .utils.photo_helpers import PhotoHelper
from .utils.hold_validator import HoldValidator

_logger = logging.getLogger(__name__)


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def _prepare_new_lot_vals(self):
        """Multiempresa: el core solo pone compañía al lote si el PRODUCTO
        tiene compañía; con productos compartidos el lote nacía sin compañía
        (visible para todas). Una placa es física y pertenece a la compañía
        que la recibe: se fija la del movimiento (igual que los lotes que
        crea el packing list)."""
        vals = super()._prepare_new_lot_vals()
        if not vals.get('company_id') and self.company_id:
            vals['company_id'] = self.company_id.id
        return vals

    # Estados donde una línea de movimiento sigue comprometiendo el lote.
    # Se excluye únicamente cancel.
    _LOT_COMMITMENT_STATES = [
        'draft',
        'waiting',
        'confirmed',
        'partially_available',
        'assigned',
        'done',
    ]

    # ==================== CAMPOS TEMPORALES DE DIMENSIONES ====================

    x_color_temp = fields.Char(
        string='Color',
        help='Color del producto (se guardará en el lote)',
    )

    # Corrección: fields.Char no acepta digits.
    x_grosor_temp = fields.Char(
        string='Grosor (cm)',
        help='Grosor del producto en centímetros (se guardará en el lote)',
    )

    x_alto_temp = fields.Float(
        string='Alto (m)',
        digits=(10, 4),
        help='Alto del producto en metros (se guardará en el lote)',
    )

    x_ancho_temp = fields.Float(
        string='Largo (m)',
        digits=(10, 4),
        help='Largo del producto en metros (se guardará en el lote)',
    )

    x_tipo_temp = fields.Selection(
        [('placa', 'Placa'), ('formato', 'Formato'), ('pieza', 'Pieza')],
        string='Tipo',
        help='Tipo de producto (se guardará en el lote)',
    )

    x_numero_placa_temp = fields.Char(
        string='No. Placa',
        help='Número de placa (se guardará en el lote)',
    )

    x_bloque_temp = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen (se guardará en el lote)',
    )

    x_atado_temp = fields.Char(
        string='Atado',
        help='Identificación del atado (se guardará en el lote)',
    )

    x_grupo_temp = fields.Many2many(
        'stock.lot.group',
        string='Grupo',
        help='Grupos del lote (se guardarán en el lote)',
    )

    x_pedimento_temp = fields.Char(
        string='Pedimento',
        help='Número de pedimento (se guardará en el lote)',
    )

    x_contenedor_temp = fields.Char(
        string='Contenedor',
        help='Número de contenedor (se guardará en el lote)',
    )

    x_referencia_proveedor_temp = fields.Char(
        string='Referencia Proveedor',
        help='Referencia del proveedor (se guardará en el lote)',
    )

    x_proveedor_temp = fields.Char(
        string='Proveedor',
    )

    x_origen_temp = fields.Char(
        string='Origen',
    )

    x_peso_temp = fields.Float(
        string='Peso (kg)',
        digits=(10, 3),
        help='Peso del producto en kg (se guardará en el lote)',
    )

    # ==================== CAMPOS COMPUTADOS ====================

    x_is_incoming = fields.Boolean(
        string='Es Recepción',
        compute='_compute_is_incoming',
        store=False,
    )

    # ==================== CAMPOS RELATED DEL LOTE ====================

    x_color_lote = fields.Char(
        related='lot_id.x_color',
        string='Color Lote',
        readonly=True,
        store=False,
    )

    x_grosor_lote = fields.Char(
        related='lot_id.x_grosor',
        string='Grosor Lote (cm)',
        readonly=True,
        store=False,
    )

    x_alto_lote = fields.Float(
        related='lot_id.x_alto',
        string='Alto Lote (m)',
        readonly=True,
        store=False,
    )

    x_ancho_lote = fields.Float(
        related='lot_id.x_ancho',
        string='Largo Lote (m)',
        readonly=True,
        store=False,
    )

    x_tipo_lote = fields.Selection(
        related='lot_id.x_tipo',
        string='Tipo Lote',
        readonly=True,
        store=False,
    )

    x_numero_placa_lote = fields.Char(
        related='lot_id.x_numero_placa',
        string='No. Placa Lote',
        readonly=True,
        store=False,
    )

    x_bloque_lote = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque Lote',
        readonly=True,
        store=False,
    )

    x_atado_lote = fields.Char(
        related='lot_id.x_atado',
        string='Atado Lote',
        readonly=True,
        store=False,
    )

    x_grupo_lote = fields.Many2many(
        related='lot_id.x_grupo',
        string='Grupo Lote',
        readonly=True,
        store=False,
    )

    x_pedimento_lote = fields.Char(
        related='lot_id.x_pedimento',
        string='Pedimento Lote',
        readonly=True,
        store=False,
    )

    x_contenedor_lote = fields.Char(
        related='lot_id.x_contenedor',
        string='Contenedor Lote',
        readonly=True,
        store=False,
    )

    x_referencia_proveedor_lote = fields.Char(
        related='lot_id.x_referencia_proveedor',
        string='Ref. Proveedor Lote',
        readonly=True,
        store=False,
    )

    x_proveedor_lote = fields.Char(
        related='lot_id.x_proveedor',
        string='Proveedor Lote',
        readonly=True,
    )

    x_origen_lote = fields.Char(
        related='lot_id.x_origen',
        string='Origen Lote',
        readonly=True,
    )

    x_fotografia_principal_lote = fields.Binary(
        related='lot_id.x_fotografia_principal',
        string='Foto Lote',
        readonly=True,
        store=False,
    )

    x_cantidad_fotos_lote = fields.Integer(
        related='lot_id.x_cantidad_fotos',
        string='# Fotos Lote',
        readonly=True,
        store=False,
    )

    # ==================== HELPERS DE VALIDACIÓN GLOBAL ====================

    def _get_qty_field_name(self):
        """
        Odoo 19 usa quantity en stock.move.line.
        Se conserva fallback a qty_done para evitar errores si alguna base trae compatibilidad.
        """
        return 'quantity' if 'quantity' in self._fields else 'qty_done'

    def _get_line_reserved_qty(self, line):
        qty_field = self._get_qty_field_name()
        return float(getattr(line, qty_field, 0.0) or 0.0)

    def _get_sale_order_from_move_line(self, line):
        """
        Resuelve la SO relacionada desde:
        1. move_id.sale_line_id.order_id
        2. picking.sale_id, si existe
        3. picking.origin exacto
        """
        SaleOrder = self.env['sale.order'].sudo()

        if line.move_id and line.move_id.sale_line_id and line.move_id.sale_line_id.order_id:
            return line.move_id.sale_line_id.order_id.sudo()

        picking = line.picking_id
        if picking and 'sale_id' in picking._fields and picking.sale_id:
            return picking.sale_id.sudo()

        if picking and picking.origin:
            # sudo salta las reglas y el folio se repite entre compañías:
            # la SO buscada por origin es la de la compañía del picking.
            so_domain = [('name', '=', picking.origin)]
            if picking.company_id:
                so_domain.append(('company_id', '=', picking.company_id.id))
            sale_order = SaleOrder.search(so_domain, limit=1)
            if sale_order:
                return sale_order

        return SaleOrder.browse()

    def _is_sale_related_move_line(self, line):
        return bool(self._get_sale_order_from_move_line(line))

    def _should_validate_duplicate_lot_commitment(self, line):
        """
        La defensa final aplica sobre movimientos con lote en operaciones no canceladas.

        Se omiten:
        - líneas sin lote/producto/ubicación
        - líneas canceladas
        - recepciones incoming
        - líneas sin picking, como ajustes de inventario
        """
        if self.env.context.get('skip_duplicate_lot_validation'):
            return False

        if not line.lot_id or not line.product_id or not line.location_id:
            return False

        if line.state == 'cancel':
            return False

        if not line.picking_id:
            return False

        if line.picking_id.picking_type_code == 'incoming':
            return False

        # DEVOLUCIONES: operación CORRECTIVA — nunca la bloquea un
        # compromiso comercial (sin esto había abrazo mortal: no puedes
        # devolver sin liberar la venta, y liberar es lo que la devolución
        # implica). Se avisa en el chatter de las ventas afectadas.
        pick = line.picking_id
        is_return = bool(
            ('return_id' in pick._fields and pick.return_id)
            or (pick.origin or '').lower().startswith(('devolución de',
                                                       'devolucion de',
                                                       'return of'))
        )
        if is_return:
            self._som_warn_sales_of_returned_lot(line)
            return False

        if self._get_line_reserved_qty(line) <= 0:
            return False

        # Un MOVIMIENTO DE BIN (reacomodo físico) siempre está permitido,
        # aunque el lote esté reservado por una venta: la reserva se
        # traspasa a la ubicación nueva (ver inventory_shopping_cart,
        # _som_displace_strong_reservations / reanclaje al validar).
        if self._is_bin_move_line(line):
            return False

        return True

    def _is_bin_move_line(self, line):
        """Reacomodo físico puro: traslado interno→interna SIN liga a venta.

        Cubre los traslados del carrito/escáner ('Carrito - %') y los
        traslados internos manuales del backend. Un picking interno que SÍ
        pertenece a la cadena de una venta (sale_line_id, group con venta,
        picking.sale_id) NO es reacomodo y sigue validándose.
        """
        picking = line.picking_id
        if not picking or picking.picking_type_code != 'internal':
            return False

        if (picking.origin or '').startswith('Carrito - '):
            return True

        move = line.move_id
        if move and move.sale_line_id:
            return False
        # Odoo 19: stock.move ya NO tiene group_id (AttributeError); el grupo
        # de aprovisionamiento se consulta por nombre de campo, tolerando
        # renombres entre builds.
        if move:
            for group_field in ('group_id', 'procure_group_id'):
                if group_field not in move._fields:
                    continue
                group = move[group_field]
                if group and 'sale_id' in group._fields and group.sale_id:
                    return False
                break
        if 'sale_id' in picking._fields and picking.sale_id:
            return False
        if 'group_id' in picking._fields and picking.group_id:
            group = picking.group_id
            if 'sale_id' in group._fields and group.sale_id:
                return False

        return bool(
            line.location_dest_id
            and line.location_dest_id.usage == 'internal'
        )

    def _som_warn_sales_of_returned_lot(self, line):
        """Aviso (no bloqueo) a las ventas vivas que traen el lote que se
        está DEVOLVIENDO: su material asignado salió por devolución."""
        try:
            sols = self.env['sale.order.line'].sudo().search([
                ('lot_ids', 'in', line.lot_id.id),
                ('order_id.state', 'in', ('draft', 'sent', 'sale')),
            ])
            for order in sols.mapped('order_id'):
                order.message_post(body=(
                    '⚠ El lote %s asignado a esta orden salió en una '
                    'DEVOLUCIÓN (%s). Revisa la asignación de material.'
                ) % (line.lot_id.name, line.picking_id.name))
        except Exception:
            _logger.exception(
                '[LOT_RETURN] No se pudo avisar a las ventas del lote '
                'devuelto %s.', line.lot_id.name)

    def _get_duplicate_lot_blockers(self, line):
        """
        Busca otras líneas activas/no canceladas que ya comprometen el mismo
        lote físico desde la misma ubicación.

        La llave lógica corresponde al quant:
        product_id + lot_id + location_id + company_id + package_id + owner_id.

        IMPORTANTE: se excluyen las líneas que pertenecen a la MISMA venta que la
        línea actual. El mismo lote moviéndose dentro del flujo de un mismo pedido
        (p. ej. PICK -> OUT en almacén de 2 pasos) no debe considerarse duplicado.
        """
        StockMoveLine = self.sudo()
        qty_field = self._get_qty_field_name()

        domain = [
            ('id', '!=', line.id),
            ('product_id', '=', line.product_id.id),
            ('lot_id', '=', line.lot_id.id),
            ('location_id', '=', line.location_id.id),
            ('state', 'in', self._LOT_COMMITMENT_STATES),
            ('picking_id', '!=', False),
            (qty_field, '>', 0),
        ]

        if line.company_id:
            domain.append(('company_id', '=', line.company_id.id))

        if line.package_id:
            domain.append(('package_id', '=', line.package_id.id))
        else:
            domain.append(('package_id', '=', False))

        if line.owner_id:
            domain.append(('owner_id', '=', line.owner_id.id))
        else:
            domain.append(('owner_id', '=', False))

        blockers = StockMoveLine.search(domain)

        # No bloquear recepciones. Sí bloquear internos ABIERTOS, salidas y
        # hechos de venta. Un traslado INTERNO ya HECHO es historia: el lote
        # solo cambió de ubicación (y pudo regresar); no es un compromiso y
        # bloqueaba para siempre re-mover el lote desde esa ubicación
        # (p. ej. movimientos del carrito/escáner SOM/INT hechos).
        blockers = blockers.filtered(
            lambda ml:
                ml.picking_id
                and ml.picking_id.picking_type_code != 'incoming'
                and ml.state != 'cancel'
                and not (
                    ml.state == 'done'
                    and ml.picking_id.picking_type_code == 'internal'
                )
                # Un traslado interno de carrito/escáner ABIERTO es una
                # reserva DÉBIL (reacomodo de ubicación): nunca bloquea a
                # ventas, entregas, apartados ni a otros traslados. Los
                # flujos fuertes lo liberan solos vía
                # stock.picking._release_cart_internal_reservations()
                # (inventory_shopping_cart); aquí simplemente no cuenta
                # como compromiso. Al revés SÍ: una venta/entrega activa
                # sigue bloqueando que el escáner mueva el lote.
                and not (
                    ml.picking_id.picking_type_code == 'internal'
                    and (ml.picking_id.origin or '').startswith('Carrito - ')
                )
        )

        # Entrega HECHA cuyo material ya REGRESÓ por devolución validada:
        # es historia, no compromiso. Sin esto, la salida done del pedido
        # original bloqueaba para siempre reusar el lote en otro pedido
        # aunque el inventario ya lo mostrara libre (caso V/310 → V/366).
        blockers = blockers.filtered(
            lambda ml: not self._som_delivery_spent_by_return(ml)
        )

        # Excluir líneas del mismo pedido de venta SOLO si viven en OTRO
        # picking (la cadena PICK→OUT del mismo pedido no es conflicto).
        # DENTRO del mismo picking sí lo es: dos líneas de venta del mismo
        # pedido compartiendo la placa generan dos moves que la reservan
        # doble (caso V/229: reservado al doble del físico).
        #
        # PERO: dos moves del mismo picking que trazan a la MISMA línea de
        # venta son una RECONSTRUCCIÓN (el re-sync de la entrega tras
        # desasignar/ajustar recrea el move y su línea vieja seguía viva un
        # instante), no una doble reserva. Contarla como bloqueador hacía
        # imposible desasignar: quitar una placa re-sincronizaba la entrega
        # y el candado tronaba con los lotes RESTANTES de la propia línea.
        def _ml_sale_line(ml):
            move = ml.move_id
            return move.sale_line_id if (
                move and 'sale_line_id' in move._fields) else False

        current_so = self._get_sale_order_from_move_line(line)
        if current_so:
            current_sale_line = _ml_sale_line(line)
            blockers = blockers.filtered(
                lambda ml: self._get_sale_order_from_move_line(ml) != current_so
                or (line.picking_id and ml.picking_id == line.picking_id
                    and ml.move_id != line.move_id
                    and (
                        not current_sale_line
                        or _ml_sale_line(ml) != current_sale_line
                    ))
            )

        return blockers

    def _som_delivery_spent_by_return(self, ml):
        """True si `ml` es una línea HECHA de salida cuyo lote ya volvió por
        una devolución VALIDADA de ese mismo picking (cantidad cubierta).

        Solo neutraliza salidas done: las operaciones abiertas siguen
        contando como compromiso normal."""
        if ml.state != 'done' or not ml.picking_id or not ml.lot_id:
            return False
        if ml.picking_id.picking_type_code == 'incoming':
            return False

        Picking = self.env['stock.picking'].sudo()
        pk = ml.picking_id
        domain = [('state', '=', 'done'), ('id', '!=', pk.id)]
        if pk.company_id:
            # sudo: las devoluciones son de la compañía del picking
            domain.append(('company_id', '=', pk.company_id.id))
        if 'return_id' in Picking._fields:
            domain = ['|', ('return_id', '=', pk.id),
                      ('origin', 'in', ['Devolución de %s' % pk.name,
                                        'Return of %s' % pk.name])] + domain
        else:
            domain = [('origin', 'in', ['Devolución de %s' % pk.name,
                                        'Return of %s' % pk.name])] + domain
        returns = Picking.search(domain)
        if not returns:
            return False

        qty_field = self._get_qty_field_name()
        delivered = sum(
            (out_ml[qty_field] or 0.0)
            for out_ml in pk.move_line_ids
            if out_ml.lot_id.id == ml.lot_id.id and out_ml.state == 'done'
        )
        returned = sum(
            (ret_ml[qty_field] or 0.0)
            for ret_ml in returns.mapped('move_line_ids')
            if ret_ml.lot_id.id == ml.lot_id.id and ret_ml.state == 'done'
        )
        return returned + 0.0001 >= delivered

    def _format_blocker_document(self, blocker):
        picking = blocker.picking_id
        sale_order = self._get_sale_order_from_move_line(blocker)

        picking_name = picking.name if picking else 'Sin picking'
        origin = picking.origin if picking else ''

        if sale_order:
            return f"{picking_name} / {sale_order.name}"

        if origin:
            return f"{picking_name} / {origin}"

        return picking_name

    def _raise_duplicate_lot_error(self, line, blockers):
        docs = []
        for blocker in blockers:
            docs.append(self._format_blocker_document(blocker))

        docs_txt = ', '.join(sorted(set(docs))) or 'Operación activa no identificada'

        current_doc = self._format_blocker_document(line)

        raise UserError(
            f"No se puede asignar el lote {line.lot_id.name}.\n\n"
            f"Este lote ya se encuentra comprometido en otra operación activa.\n\n"
            f"Producto: {line.product_id.display_name}\n"
            f"Ubicación origen: {line.location_id.complete_name}\n"
            f"Documento existente: {docs_txt}\n"
            f"Documento actual: {current_doc}\n\n"
            f"Debe seleccionar otro lote o liberar/cancelar primero la operación existente."
        )

    def _validate_duplicate_lot_commitment(self):
        """
        Defensa final: evita que el mismo lote físico se guarde manualmente
        en otra operación activa desde la pestaña Operaciones/Detalles.
        """
        for line in self:
            if not line._should_validate_duplicate_lot_commitment(line):
                continue

            blockers = line._get_duplicate_lot_blockers(line)

            # PARCIALIDADES (FORMATO/PIEZA): el mismo lote SÍ puede vivir en
            # varias operaciones activas mientras la SUMA comprometida quepa
            # en el físico del quant — es la base del apartado/venta parcial.
            # Las PLACAS siguen siendo todo-o-nada.
            if blockers and line.lot_id:
                tipo = str(getattr(line.lot_id, 'x_tipo', '') or '').lower()
                if tipo in ('formato', 'pieza'):
                    qty_field = self._get_qty_field_name()
                    quants = self.env['stock.quant'].sudo().search([
                        ('product_id', '=', line.product_id.id),
                        ('lot_id', '=', line.lot_id.id),
                        ('location_id', '=', line.location_id.id),
                        ('quantity', '>', 0),
                    ])
                    fisico = sum(quants.mapped('quantity'))
                    # Las salidas HECHAS ya descontaron su consumo del
                    # quant: sumarlas contra el físico ACTUAL las contaba
                    # DOBLE y bloqueaba el remanente legítimo (caso
                    # 15767-9: físico restante 2.00 y "comprometido" 7.77
                    # de una OUT ya validada → restante 0). Solo las
                    # operaciones ABIERTAS comprometen contra el físico.
                    open_blockers = blockers.filtered(
                        lambda b: b.state != 'done')
                    if not open_blockers:
                        # Solo la respaldan operaciones HECHAS (su consumo ya
                        # vive en el quant): no hay competencia ACTIVA por el
                        # lote y no hay nada que sumar. Además este chequeo
                        # corre en la ubicación EXACTA de la línea — en la
                        # cadena de 2 pasos eso es SOM/Salida, donde el
                        # material solo está de paso y el físico da 0:
                        # bloqueaba con 'Físico 0.00 · comprometido 0.00'.
                        continue
                    ya_comprometido = sum(
                        b[qty_field] or 0.0 for b in open_blockers)
                    intento = line[qty_field] or 0.0
                    if ya_comprometido + intento <= fisico + 0.0001:
                        continue
                    # Excede el remanente: error CON NÚMEROS (el genérico
                    # de duplicado dejaba adivinando cuánto quedaba).
                    restante = max(fisico - ya_comprometido, 0.0)
                    docs = ', '.join(sorted({
                        self._format_blocker_document(b)
                        for b in open_blockers})) or '—'
                    raise UserError(
                        f"No se puede asignar {intento:.2f} del lote "
                        f"{line.lot_id.name}: excede su remanente libre.\n\n"
                        f"Físico del lote: {fisico:.2f}\n"
                        f"Ya comprometido en otras operaciones: "
                        f"{ya_comprometido:.2f} ({docs})\n"
                        f"Restante disponible: {restante:.2f}\n\n"
                        f"Ajusta tu parcialidad a máximo {restante:.2f}, "
                        f"o libera primero la operación existente."
                    )

            # BLOQUEADORES QUE SON DEVOLUCIONES: la devolución es
            # correctiva y GANA — no debe impedir el re-sync de la entrega
            # que su propia validación dispara (cadena circular: validar la
            # devolución reescribe las mls de la venta y el candado veía a
            # la devolución como bloqueador). La venta recibe aviso para
            # reasignar el material.
            if blockers:
                def _is_return_pick(pk):
                    return bool(
                        ('return_id' in pk._fields and pk.return_id)
                        or (pk.origin or '').lower().startswith(
                            ('devolución de', 'devolucion de', 'return of'))
                    )
                return_blockers = blockers.filtered(
                    lambda b: b.picking_id and _is_return_pick(b.picking_id))
                if return_blockers and return_blockers == blockers:
                    for rb in return_blockers:
                        _logger.info(
                            '[LOT_DUPLICATE] Bloqueador %s es DEVOLUCIÓN: '
                            'se permite %s y se avisa a la venta.',
                            rb.picking_id.name, line.lot_id.name)
                    self._som_warn_sales_of_returned_lot(return_blockers[:1])
                    continue

            if blockers:
                _logger.warning(
                    "[LOT_DUPLICATE_BLOCKED] Lote=%s Producto=%s Línea=%s Picking=%s Bloqueadores=%s",
                    line.lot_id.name,
                    line.product_id.display_name,
                    line.id,
                    line.picking_id.name if line.picking_id else False,
                    blockers.ids,
                )
                line._raise_duplicate_lot_error(line, blockers)

        return True

    def _should_validate_hold_for_line(self, line):
        """
        Valida holds para operaciones de venta/recolección/salida.
        Antes solo aplicaba a outgoing. Ahora también cubre pickings internos
        ligados a venta, como SOM: Recolectar.
        """
        if self.env.context.get('skip_hold_validation'):
            return False

        if not line.lot_id or not line.picking_id or not line.location_id:
            return False

        if line.picking_id.picking_type_code == 'incoming':
            return False

        # Aplica a salidas y a operaciones internas con cliente/venta.
        if line.picking_id.picking_type_code == 'outgoing':
            return True

        if self._is_sale_related_move_line(line):
            return True

        if line.picking_id.partner_id:
            return True

        return False

    def _validate_hold_for_lines(self, forced_lot_id=False):
        validator = HoldValidator(self.env)

        for line in self:
            if not line._should_validate_hold_for_line(line):
                continue

            lot_id = forced_lot_id or line.lot_id.id
            if not lot_id:
                continue

            partner = validator.get_customer_from_picking(line)
            if not partner:
                continue

            company_id = (
                line.picking_id.company_id.id
                if line.picking_id.company_id
                else self.env.company.id
            )

            validator.validate_lot_assignment(
                lot_id,
                line.location_id.id,
                partner.id,
                company_id,
            )

        return True

    def _get_available_lots_domain_for_line(self):
        """
        Dominio para onchange de lot_id:
        - respeta holds por cliente
        - excluye lotes ya comprometidos en otra operación activa

        Los lotes comprometidos por líneas de la MISMA venta NO se excluyen,
        para permitir el flujo de un mismo pedido en almacén de 2 pasos.
        """
        self.ensure_one()

        if not self.product_id or not self.location_id or not self.picking_id:
            return [('id', '=', False)]

        validator = HoldValidator(self.env)
        partner = validator.get_customer_from_picking(self)

        company_id = (
            self.picking_id.company_id.id
            if self.picking_id.company_id
            else self.env.company.id
        )

        available_lots = []

        if partner:
            available_lots = validator.get_available_lots(
                self.product_id.id,
                self.location_id.id,
                partner.id,
                company_id,
            )
        else:
            quants = self.env['stock.quant'].sudo().search([
                ('product_id', '=', self.product_id.id),
                ('location_id', '=', self.location_id.id),
                ('quantity', '>', 0),
                ('company_id', '=', company_id),
            ])
            available_lots = quants.mapped('lot_id').ids

        if not available_lots:
            return [('id', '=', False)]

        qty_field = self._get_qty_field_name()
        blocked_lines = self.env['stock.move.line'].sudo().search([
            ('id', '!=', self.id or 0),
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id),
            ('lot_id', 'in', available_lots),
            ('state', 'in', self._LOT_COMMITMENT_STATES),
            ('picking_id', '!=', False),
            (qty_field, '>', 0),
        ])

        blocked_lines = blocked_lines.filtered(
            lambda ml:
                ml.picking_id
                and ml.picking_id.picking_type_code != 'incoming'
                and ml.state != 'cancel'
                # Mismos criterios que _get_duplicate_lot_blockers: un
                # interno HECHO es historia y un interno de carrito/escáner
                # ABIERTO es reserva débil — ninguno debe esconder el lote
                # del selector.
                and not (
                    ml.state == 'done'
                    and ml.picking_id.picking_type_code == 'internal'
                )
                and not (
                    ml.picking_id.picking_type_code == 'internal'
                    and (ml.picking_id.origin or '').startswith('Carrito - ')
                )
        )

        # No considerar bloqueadores de la misma venta.
        current_so = self._get_sale_order_from_move_line(self)
        if current_so:
            blocked_lines = blocked_lines.filtered(
                lambda ml: self._get_sale_order_from_move_line(ml) != current_so
            )

        blocked_lot_ids = set(blocked_lines.mapped('lot_id').ids)

        # Si la línea actual ya tiene lote, conservarlo en dominio para no romper edición visual.
        if self.lot_id:
            blocked_lot_ids.discard(self.lot_id.id)

        final_lot_ids = [lot_id for lot_id in available_lots if lot_id not in blocked_lot_ids]

        if final_lot_ids:
            return [
                ('id', 'in', final_lot_ids),
                ('product_id', '=', self.product_id.id),
            ]

        return [('id', '=', False)]

    # ==================== MÉTODOS COMPUTADOS ====================

    @api.depends('picking_id', 'picking_id.picking_type_code')
    def _compute_is_incoming(self):
        """Determinar si la línea pertenece a una recepción."""
        for line in self:
            line.x_is_incoming = (
                line.picking_id
                and line.picking_id.picking_type_code == 'incoming'
            )

    # ==================== VALIDACIONES ====================

    @api.constrains(
        'lot_id',
        'product_id',
        'location_id',
        'picking_id',
        'move_id',
        'state',
        'package_id',
        'owner_id',
        'company_id',
    )
    def _check_lot_hold_and_duplicate_commitment(self):
        """
        Validación ORM final.

        Cubre:
        - holds activos de otro cliente
        - el mismo lote ya comprometido en otra operación no cancelada
        """
        self._validate_hold_for_lines()
        self._validate_duplicate_lot_commitment()

    # ==================== ONCHANGE - FILTRADO DE LOTES ====================

    @api.onchange('product_id', 'location_id', 'picking_id')
    def _onchange_product_location_filter_lots(self):
        """
        Filtra lotes disponibles según holds y reservas nativas activas.

        Antes solo aplicaba en outgoing. Ahora también aplica a recolecciones
        internas vinculadas a ventas.
        """
        if not self.product_id or not self.picking_id:
            return {}

        if self.picking_id.picking_type_code == 'incoming':
            return {}

        if not self.location_id:
            return {'domain': {'lot_id': [('id', '=', False)]}}

        return {
            'domain': {
                'lot_id': self._get_available_lots_domain_for_line(),
            }
        }

    # ==================== ONCHANGE - DIMENSIONES ====================

    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """Cargar dimensiones del lote y calcular cantidad."""
        if not self.lot_id:
            return

        LotDimensionSync.load_dimensions_from_lot(self)

        if not self.picking_id:
            return

        qty_field = self._get_qty_field_name()

        if self.picking_id.picking_type_code == 'incoming':
            self[qty_field] = LotDimensionSync.calculate_area(
                self.lot_id.x_alto,
                self.lot_id.x_ancho,
            )

        elif self.picking_id.picking_type_code == 'outgoing':
            move_qty = self.move_id.product_uom_qty if self.move_id else None

            self[qty_field] = LotDimensionSync.get_available_quantity(
                self.env,
                self.lot_id.id,
                self.location_id.id,
                self.product_id.id,
                move_qty,
            )

    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular qty_done automáticamente cuando se ingresan dimensiones."""
        if not self.picking_id or self.picking_id.picking_type_code != 'incoming':
            return

        self[self._get_qty_field_name()] = LotDimensionSync.calculate_area(
            self.x_alto_temp,
            self.x_ancho_temp,
        )

    # ==================== WRITE ====================

    def write(self, vals):
        """
        Guarda dimensiones y valida:
        - holds
        - duplicidad de lote en operaciones no canceladas
        """
        if 'lot_id' in vals and vals['lot_id']:
            self._validate_hold_for_lines(forced_lot_id=vals['lot_id'])

        result = super().write(vals)

        self._validate_duplicate_lot_commitment()

        self._sync_dimensions_to_lot(vals)
        self._update_qty_done_if_needed(vals)

        return result

    def _sync_dimensions_to_lot(self, vals):
        """Sincroniza dimensiones temporales al lote."""
        dimension_fields = list(LotDimensionSync.DIMENSION_MAPPING.keys())
        has_dimensions = any(field in vals for field in dimension_fields)

        if 'lot_id' not in vals and not has_dimensions:
            return

        for line in self:
            if not line.lot_id or not line.picking_id:
                continue

            if line.picking_id.picking_type_code != 'incoming':
                continue

            lot_vals = LotDimensionSync.sync_dimensions_to_lot(line)

            if lot_vals:
                line.lot_id.write(lot_vals)

    def _update_qty_done_if_needed(self, vals):
        """Actualiza qty_done si cambiaron dimensiones."""
        qty_field = self._get_qty_field_name()

        if ('x_alto_temp' not in vals and 'x_ancho_temp' not in vals) or qty_field in vals:
            return

        for line in self:
            if not line.picking_id or line.picking_id.picking_type_code != 'incoming':
                continue

            qty_done = LotDimensionSync.calculate_area(
                line.x_alto_temp,
                line.x_ancho_temp,
            )

            if qty_done > 0:
                super(StockMoveLine, line).write({qty_field: qty_done})

    # ==================== CREATE ====================

    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y validar duplicidad al crear."""
        for vals in vals_list:
            picking_id = vals.get('picking_id')
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.picking_type_code == 'incoming':
                    qty_done = LotDimensionSync.calculate_area(
                        vals.get('x_alto_temp'),
                        vals.get('x_ancho_temp'),
                    )
                    if qty_done > 0:
                        vals[self._get_qty_field_name()] = qty_done

        lines = super().create(vals_list)

        lines._validate_hold_for_lines()
        lines._validate_duplicate_lot_commitment()

        for line in lines:
            if not line.lot_id or not line.picking_id:
                continue

            if line.picking_id.picking_type_code != 'incoming':
                continue

            lot_vals = LotDimensionSync.sync_dimensions_to_lot(line)
            if lot_vals:
                line.lot_id.write(lot_vals)

        return lines

    # ==================== ACCIONES ====================

    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote."""
        self.ensure_one()

        if not self.lot_id:
            return NotificationBuilder.build_warning(
                'Advertencia',
                'Debe seleccionar un lote primero',
            )

        return {
            'name': 'Agregar Fotografía',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lot_id': self.lot_id.id,
                'default_name': f'Foto - {self.lot_id.name}',
            },
        }

    def action_view_lot_photos(self):
        """Ver fotografías del lote."""
        self.ensure_one()

        if not self.lot_id:
            raise UserError('Debe seleccionar un lote primero.')

        return PhotoHelper.build_photo_gallery_action(
            self.lot_id.id,
            self.lot_id.name,
        )