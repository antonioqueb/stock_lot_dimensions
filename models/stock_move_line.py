# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)

class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    # Campos temporales para captura en recepción
    x_grosor_temp = fields.Float(
        string='Grosor (cm)',
        digits=(10, 2),
        help='Grosor del producto en centímetros (se guardará en el lote)'
    )
    
    x_alto_temp = fields.Float(
        string='Alto (m)',
        digits=(10, 4),
        help='Alto del producto en metros (se guardará en el lote)'
    )
    
    x_ancho_temp = fields.Float(
        string='Ancho (m)',
        digits=(10, 4),
        help='Ancho del producto en metros (se guardará en el lote)'
    )
    
    x_bloque_temp = fields.Char(
        string='Bloque',
        help='Identificación del bloque de origen (se guardará en el lote)'
    )

    x_atado_temp = fields.Char(
        string='Atado',
        help='Identificación del atado (se guardará en el lote)'
    )
    
    x_formato_temp = fields.Selection([
        ('placa', 'Placa'),
        ('060x120', '0.60 x 1.20 m'),
        ('060x060', '0.60 x 0.60 m'),
        ('060x040', '0.60 x 0.40 m'),
        ('060x020', '0.60 x 0.20 m'),
        ('060x010', '0.60 x 0.10 m'),
        ('060x030', '0.60 x 0.30 m'),
        ('060xll', '0.60 x LL m'),
        ('050xll', '0.50 x LL m'),
        ('040xll', '0.40 x LL m'),
        ('010xll', '0.10 x LL m'),
        ('005xll', '0.05 x LL m'),
        ('080x160', '0.80 x 1.60 m'),
        ('075x150', '0.75 x 1.50 m'),
        ('320x160', '3.20 x 1.60 m'),
        ('020xll', '0.20 x LL m'),
        ('015xll', '0.15 x LL m'),
        ('122x061', '1.22 x 0.61 m'),
        ('100x050', '1.00 x 0.50 m'),
        ('100x025', '1.00 x 0.25 m'),
        ('120x278', '1.20 x 2.78 m'),
        ('300x100', '3.00 x 1.00 m'),
        ('324x162', '3.24 x 1.62 m'),
    ], string='Formato', default='placa', help='Formato del producto (se guardará en el lote)')
    
    # Campo computed para saber si es recepción
    x_is_incoming = fields.Boolean(
        string='Es Recepción',
        compute='_compute_is_incoming',
        store=False
    )
    
    # Campos related para mostrar en historial de movimientos
    x_grosor_lote = fields.Float(
        related='lot_id.x_grosor',
        string='Grosor Lote (cm)',
        readonly=True,
        store=False
    )
    
    x_alto_lote = fields.Float(
        related='lot_id.x_alto',
        string='Alto Lote (m)',
        readonly=True,
        store=False
    )
    
    x_ancho_lote = fields.Float(
        related='lot_id.x_ancho',
        string='Ancho Lote (m)',
        readonly=True,
        store=False
    )
    
    x_bloque_lote = fields.Char(
        related='lot_id.x_bloque',
        string='Bloque Lote',
        readonly=True,
        store=False
    )

    x_atado_lote = fields.Char(
        related='lot_id.x_atado',
        string='Atado Lote',
        readonly=True,
        store=False
    )
    
    x_formato_lote = fields.Selection(
        related='lot_id.x_formato',
        string='Formato Lote',
        readonly=True,
        store=False
    )
    
    x_fotografia_principal_lote = fields.Binary(
        related='lot_id.x_fotografia_principal',
        string='Foto Lote',
        readonly=True,
        store=False
    )
    
    x_cantidad_fotos_lote = fields.Integer(
        related='lot_id.x_cantidad_fotos',
        string='# Fotos Lote',
        readonly=True,
        store=False
    )

    @api.depends('picking_id', 'picking_id.picking_type_code')
    def _compute_is_incoming(self):
        """Determinar si la línea pertenece a una recepción"""
        for line in self:
            line.x_is_incoming = line.picking_id and line.picking_id.picking_type_code == 'incoming'

    def _get_lotes_disponibles_ids(self):
        """
        🔍 FILTRADO DE LOTES - CON DEPURACIÓN COMPLETA
        """
        self.ensure_one()
        
        _logger.info("🔵"*50)
        _logger.info("🔵 [FILTRO LOTES] _get_lotes_disponibles_ids() INICIANDO")
        _logger.info("🔵 [FILTRO LOTES] Move Line ID: %s", self.id)
        
        # Solo aplicar filtro en pickings de salida (entregas)
        if not self.picking_id:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY PICKING - Retornando lista vacía")
            return []
            
        if self.picking_id.picking_type_code != 'outgoing':
            _logger.info("🔵 [FILTRO LOTES] ⏭️ Picking NO es outgoing (es: %s) - No filtrar", 
                        self.picking_id.picking_type_code)
            return []
        
        _logger.info("🔵 [FILTRO LOTES] ✅ Picking es OUTGOING: %s", self.picking_id.name)
        
        # Obtener el cliente del picking
        cliente_picking = self.picking_id.partner_id
        _logger.info("🔵 [FILTRO LOTES] Cliente del picking: %s (ID: %s)", 
                    cliente_picking.name if cliente_picking else 'SIN CLIENTE',
                    cliente_picking.id if cliente_picking else 'N/A')
        
        if self.move_id and self.move_id.sale_line_id:
            cliente_picking = self.move_id.sale_line_id.order_id.partner_id
            _logger.info("🔵 [FILTRO LOTES] ✅ Cliente actualizado desde sale_line_id: %s (ID: %s)", 
                        cliente_picking.name, cliente_picking.id)
        
        if not cliente_picking:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY CLIENTE - Retornando lista vacía")
            return []
            
        if not self.product_id:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY PRODUCTO - Retornando lista vacía")
            return []
            
        if not self.location_id:
            _logger.warning("🔵 [FILTRO LOTES] ❌ NO HAY UBICACIÓN - Retornando lista vacía")
            return []
        
        _logger.info("🔵 [FILTRO LOTES] Producto: %s (ID: %s)", self.product_id.name, self.product_id.id)
        _logger.info("🔵 [FILTRO LOTES] Ubicación: %s (ID: %s)", self.location_id.name, self.location_id.id)
        
        # Buscar todos los quants del producto en la ubicación
        quants = self.env['stock.quant'].search([
            ('product_id', '=', self.product_id.id),
            ('location_id', '=', self.location_id.id),
            ('quantity', '>', 0),
        ])
        
        _logger.info("🔵 [FILTRO LOTES] Total quants encontrados: %s", len(quants))
        
        # Filtrar lotes válidos
        lotes_validos = []
        
        for quant in quants:
            if quant.lot_id:
                lote_nombre = quant.lot_id.name
                lote_id = quant.lot_id.id
                tiene_hold = quant.x_tiene_hold
                
                _logger.info("🔵 [FILTRO LOTES] ─────────────────────────────────────")
                _logger.info("🔵 [FILTRO LOTES] Analizando Lote: %s (ID: %s)", lote_nombre, lote_id)
                _logger.info("🔵 [FILTRO LOTES] Cantidad: %.2f", quant.quantity)
                _logger.info("🔵 [FILTRO LOTES] Tiene Hold: %s", tiene_hold)
                
                # CASO 1: Sin hold → Disponible para TODOS
                if not tiene_hold:
                    _logger.info("🔵 [FILTRO LOTES] ✅ SIN HOLD - Agregando a lista válida")
                    lotes_validos.append(lote_id)
                    continue
                
                # CASO 2: Con hold → Verificar para quién es
                if quant.x_hold_activo_id:
                    hold_partner = quant.x_hold_activo_id.partner_id
                    hold_partner_id = hold_partner.id if hold_partner else None
                    hold_partner_name = hold_partner.name if hold_partner else 'SIN CLIENTE'
                    
                    _logger.info("🔵 [FILTRO LOTES] Hold encontrado:")
                    _logger.info("🔵 [FILTRO LOTES]   - Partner Hold: %s (ID: %s)", 
                                hold_partner_name, hold_partner_id)
                    _logger.info("🔵 [FILTRO LOTES]   - Partner Picking: %s (ID: %s)", 
                                cliente_picking.name, cliente_picking.id)
                    
                    if hold_partner_id == cliente_picking.id:
                        _logger.info("🔵 [FILTRO LOTES] ✅ HOLD PARA ESTE CLIENTE - Agregando a lista válida")
                        lotes_validos.append(lote_id)
                    else:
                        _logger.warning("🔵 [FILTRO LOTES] ❌ HOLD PARA OTRO CLIENTE - NO agregando")
                        _logger.warning("🔵 [FILTRO LOTES]    Este lote NO debe aparecer en la lista")
                else:
                    _logger.warning("🔵 [FILTRO LOTES] ⚠️ Tiene hold pero sin x_hold_activo_id - NO agregando")
        
        _logger.info("🔵 [FILTRO LOTES] ═════════════════════════════════════════")
        _logger.info("🔵 [FILTRO LOTES] RESUMEN FINAL:")
        _logger.info("🔵 [FILTRO LOTES] Total quants analizados: %s", len(quants))
        _logger.info("🔵 [FILTRO LOTES] Lotes válidos encontrados: %s", len(lotes_validos))
        _logger.info("🔵 [FILTRO LOTES] IDs de lotes válidos: %s", lotes_validos)
        _logger.info("🔵 [FILTRO LOTES] _get_lotes_disponibles_ids() FINALIZADO")
        _logger.info("🔵"*50)
        
        return lotes_validos

    @api.constrains('lot_id', 'picking_id', 'state')
    def _check_lot_hold(self):
        """
        🔒 CONSTRAINT: Validación de holds al asignar/confirmar lotes
        
        IMPORTANTE:
        - Respeta el contexto skip_hold_validation cuando los lotes ya fueron validados
        - Solo valida en pickings de salida (outgoing)
        - Solo valida cuando el lote ya está asignado
        - Solo valida si hay un hold activo (x_tiene_hold=True)
        - Permite holds del mismo cliente
        - Bloquea holds de otros clientes
        """
        # 🔑 BYPASS: Si el contexto indica que ya se validó, saltar
        if self._context.get('skip_hold_validation'):
            _logger.info("🔒 [CONSTRAINT] BYPASS activado - Saltando validación de holds")
            return
        
        for line in self:
            _logger.info("🔒" * 50)
            _logger.info("🔒 [CONSTRAINT] _check_lot_hold() EJECUTADO")
            _logger.info("🔒 [CONSTRAINT] Move Line ID: %s", line.id)
            _logger.info("🔒 [CONSTRAINT] Lote: %s (ID: %s)", 
                        line.lot_id.name if line.lot_id else 'Sin lote', 
                        line.lot_id.id if line.lot_id else None)
            _logger.info("🔒 [CONSTRAINT] Location: %s (ID: %s)", 
                        line.location_id.name if line.location_id else 'Sin location', 
                        line.location_id.id if line.location_id else None)
            _logger.info("🔒 [CONSTRAINT] Picking: %s", 
                        line.picking_id.name if line.picking_id else 'Sin picking')
            
            # Skip si no hay lote asignado
            if not line.lot_id:
                _logger.info("🔒 [CONSTRAINT] ⏭️ Sin lote - skipping")
                _logger.info("🔒" * 50)
                continue
            
            # Skip si no es picking de salida
            if not line.picking_id or line.picking_id.picking_type_code != 'outgoing':
                _logger.info("🔒 [CONSTRAINT] ⏭️ No es picking outgoing - skipping")
                _logger.info("🔒" * 50)
                continue
            
            # Obtener cliente del picking
            partner = line.picking_id.partner_id
            _logger.info("🔒 [CONSTRAINT] Cliente: %s (ID: %s)", 
                        partner.name if partner else 'Sin cliente',
                        partner.id if partner else None)
            
            if not partner:
                _logger.info("🔒 [CONSTRAINT] ⏭️ Sin cliente - skipping")
                _logger.info("🔒" * 50)
                continue
            
            # Buscar quant específico CON HOLD ACTIVO para este lote Y ubicación
            quant = self.env['stock.quant'].search([
                ('lot_id', '=', line.lot_id.id),
                ('location_id', '=', line.location_id.id),
                ('quantity', '>', 0),
                ('x_tiene_hold', '=', True),  # 🔑 FILTRO CRÍTICO: Solo quants con hold activo
            ], limit=1)
            
            if not quant:
                _logger.info("🔒 [CONSTRAINT] ✅ No se encontró quant con hold activo - OK para usar")
                _logger.info("🔒" * 50)
                continue
            
            _logger.info("🔒 [CONSTRAINT] ⚠️ Quant con hold encontrado - ID: %s", quant.id)
            
            hold_partner = quant.x_hold_activo_id.partner_id
            _logger.info("🔒 [CONSTRAINT] Hold para: %s (ID: %s)", 
                        hold_partner.name if hold_partner else 'Sin partner',
                        hold_partner.id if hold_partner else None)
            
            if hold_partner and hold_partner.id != partner.id:
                dias_restantes = quant.x_hold_dias_restantes
                fecha_expiracion = quant.x_hold_expira.strftime('%d/%m/%Y %H:%M') if quant.x_hold_expira else 'N/A'
                
                _logger.error("🔒 [CONSTRAINT] ❌❌❌ BLOQUEANDO - Hold para otro cliente")
                _logger.info("🔒" * 50)
                
                raise ValidationError(
                    f"🔒 NO PUEDE USAR ESTE LOTE\n\n"
                    f"El lote '{line.lot_id.name}' está RESERVADO para:\n"
                    f"👤 {hold_partner.name}\n"
                    f"📅 Hasta: {fecha_expiracion}\n"
                    f"⏱️ Días restantes: {dias_restantes}\n\n"
                    f"❌ Esta entrega es para '{partner.name}'\n\n"
                    f"Por favor, seleccione un lote disponible.\n"
                    f"Los lotes apartados para otros clientes no aparecen en la lista."
                )
            else:
                _logger.info("🔒 [CONSTRAINT] ✅ Hold es para este cliente - OK")
            
            _logger.info("🔒" * 50)

    @api.onchange('product_id', 'location_id', 'picking_id')
    def _onchange_product_location_filter_lots(self):
        """
        🎨 ONCHANGE - Filtrar lotes cuando el usuario cambia producto/ubicación
        """
        _logger.info("🟢"*50)
        _logger.info("🟢 [ONCHANGE] _onchange_product_location_filter_lots() EJECUTADO")
        
        if not self.product_id or not self.picking_id:
            _logger.info("🟢 [ONCHANGE] Sin producto o picking - retornando {}")
            return {}
        
        # Solo aplicar filtro en pickings de salida (entregas)
        if self.picking_id.picking_type_code != 'outgoing':
            _logger.info("🟢 [ONCHANGE] Picking NO es outgoing - retornando {}")
            return {}
        
        _logger.info("🟢 [ONCHANGE] Llamando a _get_lotes_disponibles_ids()...")
        lotes_validos = self._get_lotes_disponibles_ids()
        
        # Retornar dominio que filtra los lotes
        if lotes_validos:
            domain_result = {
                'domain': {
                    'lot_id': [
                        ('id', 'in', lotes_validos),
                        ('product_id', '=', self.product_id.id)
                    ]
                }
            }
            _logger.info("🟢 [ONCHANGE] ✅ Retornando dominio con %s lotes", len(lotes_validos))
            _logger.info("🟢 [ONCHANGE] Dominio: %s", domain_result)
            _logger.info("🟢"*50)
            return domain_result
        else:
            domain_result = {
                'domain': {
                    'lot_id': [('id', '=', False)]
                }
            }
            _logger.info("🟢 [ONCHANGE] ⚠️ NO HAY LOTES VÁLIDOS - Retornando dominio vacío")
            _logger.info("🟢"*50)
            return domain_result

    @api.onchange('lot_id')
    def _onchange_lot_id_dimensions(self):
        """
        Cargar dimensiones del lote si ya existen y calcular cantidad.
        """
        if self.lot_id:
            # Cargar valores en campos temporales
            self.x_grosor_temp = self.lot_id.x_grosor
            self.x_alto_temp = self.lot_id.x_alto
            self.x_ancho_temp = self.lot_id.x_ancho
            self.x_bloque_temp = self.lot_id.x_bloque
            self.x_atado_temp = self.lot_id.x_atado 
            self.x_formato_temp = self.lot_id.x_formato
            
            if self.picking_id:
                if self.picking_id.picking_type_code == 'incoming':
                    # RECEPCIÓN: Calcular por dimensiones
                    if self.lot_id.x_alto and self.lot_id.x_ancho:
                        self.qty_done = self.lot_id.x_alto * self.lot_id.x_ancho
                
                elif self.picking_id.picking_type_code == 'outgoing':
                    # ENTREGA: Buscar cantidad disponible del lote
                    quant = self.env['stock.quant'].search([
                        ('lot_id', '=', self.lot_id.id),
                        ('location_id', '=', self.location_id.id),
                        ('product_id', '=', self.product_id.id)
                    ], limit=1)
                    
                    if quant:
                        cantidad_disponible = quant.available_quantity
                        if cantidad_disponible > 0:
                            if self.move_id and self.move_id.product_uom_qty:
                                self.qty_done = min(cantidad_disponible, self.move_id.product_uom_qty)
                            else:
                                self.qty_done = cantidad_disponible
                        else:
                            self.qty_done = 0.0
                    else:
                        self.qty_done = 0.0

    @api.onchange('x_alto_temp', 'x_ancho_temp')
    def _onchange_calcular_cantidad(self):
        """Calcular automáticamente qty_done (m²) cuando se ingresan alto y ancho"""
        if self.picking_id and self.picking_id.picking_type_code == 'incoming':
            if self.x_alto_temp and self.x_ancho_temp:
                self.qty_done = self.x_alto_temp * self.x_ancho_temp

    def write(self, vals):
        """Guardar dimensiones en el lote al confirmar (solo en recepciones)"""
        _logger.info("🟣"*50)
        _logger.info("🟣 [WRITE] write() EJECUTADO en stock.move.line")
        _logger.info("🟣 [WRITE] vals: %s", vals)
        
        # ================================================================
        # VALIDACIÓN CRÍTICA: Si se está modificando lot_id, verificar hold
        # ================================================================
        if 'lot_id' in vals and vals['lot_id']:
            _logger.info("🟣 [WRITE] ⚠️ Detectado cambio de lot_id a: %s", vals['lot_id'])
            
            for line in self:
                # Solo validar en pickings de salida (entregas)
                if line.picking_id and line.picking_id.picking_type_code == 'outgoing':
                    _logger.info("🟣 [WRITE] Picking es OUTGOING - Validando hold")
                    _logger.info("🟣 [WRITE] Picking: %s", line.picking_id.name)
                    
                    # Obtener el cliente del picking
                    cliente_picking = line.picking_id.partner_id
                    if line.move_id and line.move_id.sale_line_id:
                        cliente_picking = line.move_id.sale_line_id.order_id.partner_id
                    
                    if cliente_picking:
                        _logger.info("🟣 [WRITE] Cliente picking: %s (ID: %s)", 
                                    cliente_picking.name, cliente_picking.id)
                        
                        # Buscar el quant del lote que se intenta asignar
                        new_lot = self.env['stock.lot'].browse(vals['lot_id'])
                        _logger.info("🟣 [WRITE] Nuevo lote a asignar: %s (ID: %s)", 
                                    new_lot.name, new_lot.id)
                        
                        quant = self.env['stock.quant'].search([
                            ('lot_id', '=', vals['lot_id']),
                            ('location_id', '=', line.location_id.id),
                            ('product_id', '=', line.product_id.id)
                        ], limit=1)
                        
                        if quant:
                            _logger.info("🟣 [WRITE] Quant encontrado - ID: %s", quant.id)
                            _logger.info("🟣 [WRITE] Tiene hold: %s", quant.x_tiene_hold)
                            
                            # Si tiene hold, verificar que sea para este cliente
                            if quant.x_tiene_hold and quant.x_hold_activo_id:
                                hold_partner = quant.x_hold_activo_id.partner_id
                                _logger.info("🟣 [WRITE] Hold partner: %s (ID: %s)", 
                                            hold_partner.name, hold_partner.id)
                                
                                # Si el hold NO es para este cliente, BLOQUEAR
                                if hold_partner.id != cliente_picking.id:
                                    _logger.error("🟣 [WRITE] ❌❌❌ BLOQUEANDO WRITE!")
                                    _logger.error("🟣 [WRITE] Lote tiene hold para otro cliente")
                                    
                                    raise UserError(
                                        f"🔒 NO PUEDE ASIGNAR ESTE LOTE\n\n"
                                        f"El lote '{new_lot.name}' está RESERVADO para:\n"
                                        f"👤 {hold_partner.name}\n"
                                        f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                                        f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n\n"
                                        f"❌ Esta entrega es para '{cliente_picking.name}'\n\n"
                                        f"Por favor, seleccione un lote disponible de la lista."
                                    )
                                else:
                                    _logger.info("🟣 [WRITE] ✅ Hold es para este cliente - Permitiendo")
                            else:
                                _logger.info("🟣 [WRITE] ✅ No tiene hold - Permitiendo")
                        else:
                            _logger.warning("🟣 [WRITE] ⚠️ No se encontró quant para este lote")
                    else:
                        _logger.warning("🟣 [WRITE] ⚠️ No hay cliente en el picking")
                else:
                    if line.picking_id:
                        _logger.info("🟣 [WRITE] Picking NO es outgoing (es: %s) - No validar", 
                                    line.picking_id.picking_type_code)
        
        _logger.info("🟣 [WRITE] ✅ Validaciones pasadas - Ejecutando super().write()")
        _logger.info("🟣"*50)
        
        # Primero ejecutar el write original
        result = super().write(vals)
        
        # Después del write, verificar si hay dimensiones que guardar en el lote
        dimension_fields = ['x_grosor_temp', 'x_alto_temp', 'x_ancho_temp', 'x_bloque_temp', 'x_atado_temp', 'x_formato_temp']
        has_dimensions = any(field in vals for field in dimension_fields)
        
        # Si se modificó el lote_id o hay dimensiones, actualizar el lote
        if 'lot_id' in vals or has_dimensions:
            for line in self:
                if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    lot_vals = {}
                    
                    if line.x_grosor_temp:
                        lot_vals['x_grosor'] = line.x_grosor_temp
                    if line.x_alto_temp:
                        lot_vals['x_alto'] = line.x_alto_temp
                    if line.x_ancho_temp:
                        lot_vals['x_ancho'] = line.x_ancho_temp
                    if line.x_bloque_temp:
                        lot_vals['x_bloque'] = line.x_bloque_temp
                    if line.x_atado_temp:
                        lot_vals['x_atado'] = line.x_atado_temp
                    if line.x_formato_temp:
                        lot_vals['x_formato'] = line.x_formato_temp
                    
                    if lot_vals:
                        line.lot_id.write(lot_vals)
        
        # Calcular qty_done si se modifican alto o ancho
        if ('x_alto_temp' in vals or 'x_ancho_temp' in vals) and 'qty_done' not in vals:
            for line in self:
                if line.picking_id and line.picking_id.picking_type_code == 'incoming':
                    alto = line.x_alto_temp
                    ancho = line.x_ancho_temp
                    if alto and ancho:
                        super(StockMoveLine, line).write({'qty_done': alto * ancho})
        
        return result

    @api.model_create_multi
    def create(self, vals_list):
        """Guardar dimensiones en el lote y calcular cantidad al crear"""
        for vals in vals_list:
            picking_id = vals.get('picking_id')
            if picking_id:
                picking = self.env['stock.picking'].browse(picking_id)
                if picking.picking_type_code == 'incoming':
                    if vals.get('x_alto_temp') and vals.get('x_ancho_temp'):
                        vals['qty_done'] = vals['x_alto_temp'] * vals['x_ancho_temp']
        
        lines = super().create(vals_list)
        
        for line, vals in zip(lines, vals_list):
            if line.lot_id and line.picking_id and line.picking_id.picking_type_code == 'incoming':
                lot_vals = {}
                
                if line.x_grosor_temp:
                    lot_vals['x_grosor'] = line.x_grosor_temp
                if line.x_alto_temp:
                    lot_vals['x_alto'] = line.x_alto_temp
                if line.x_ancho_temp:
                    lot_vals['x_ancho'] = line.x_ancho_temp
                if line.x_bloque_temp:
                    lot_vals['x_bloque'] = line.x_bloque_temp
                if line.x_formato_temp:
                    lot_vals['x_formato'] = line.x_formato_temp
                
                if lot_vals:
                    line.lot_id.write(lot_vals)
        
        return lines

    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        if not self.lot_id:
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': 'Advertencia',
                    'message': 'Debe seleccionar un lote primero',
                    'type': 'warning',
                }
            }
        
        return {
            'name': 'Agregar Fotografía',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lot_id': self.lot_id.id,
                'default_name': f'Foto - {self.lot_id.name}',
            }
        }
    
    def action_view_lot_photos(self):
        """Ver fotografías del lote"""
        self.ensure_one()
        if not self.lot_id:
            return False
        
        return {
            'name': f'Fotografías - {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'kanban,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
            'context': {
                'default_lot_id': self.lot_id.id,
            }
        }


class StockLot(models.Model):
    _inherit = 'stock.lot'
    
    @api.model
    def name_search(self, name='', args=None, operator='ilike', limit=100):
        """
        🔒 FILTRADO ADICIONAL - En name_search
        
        Este método se ejecuta cuando Odoo busca lotes para el selector.
        Aquí agregamos el filtrado de holds TAMBIÉN en la búsqueda.
        """
        _logger.info("🟡"*50)
        _logger.info("🟡 [NAME_SEARCH] name_search() EJECUTADO en stock.lot")
        _logger.info("🟡 [NAME_SEARCH] name: %s", name)
        _logger.info("🟡 [NAME_SEARCH] args: %s", args)
        _logger.info("🟡 [NAME_SEARCH] Context: %s", self.env.context)
        
        # Verificar si estamos en el contexto de una move_line
        move_line_id = self.env.context.get('move_line_id')
        
        if move_line_id:
            _logger.info("🟡 [NAME_SEARCH] ✅ Contexto tiene move_line_id: %s", move_line_id)
            
            move_line = self.env['stock.move.line'].browse(move_line_id)
            
            if move_line.picking_id and move_line.picking_id.picking_type_code == 'outgoing':
                _logger.info("🟡 [NAME_SEARCH] ✅ Es un picking OUTGOING - Aplicando filtro")
                
                # Obtener cliente
                cliente_picking = move_line.picking_id.partner_id
                if move_line.move_id and move_line.move_id.sale_line_id:
                    cliente_picking = move_line.move_id.sale_line_id.order_id.partner_id
                
                if cliente_picking:
                    _logger.info("🟡 [NAME_SEARCH] Cliente: %s (ID: %s)", 
                                cliente_picking.name, cliente_picking.id)
                    
                    # Buscar quants válidos
                    domain = [
                        ('product_id', '=', move_line.product_id.id),
                        ('location_id', '=', move_line.location_id.id),
                        ('quantity', '>', 0),
                    ]
                    
                    quants = self.env['stock.quant'].search(domain)
                    _logger.info("🟡 [NAME_SEARCH] Quants encontrados: %s", len(quants))
                    
                    lotes_validos = []
                    for quant in quants:
                        if quant.lot_id:
                            if not quant.x_tiene_hold:
                                lotes_validos.append(quant.lot_id.id)
                            elif quant.x_hold_activo_id and quant.x_hold_activo_id.partner_id.id == cliente_picking.id:
                                lotes_validos.append(quant.lot_id.id)
                    
                    _logger.info("🟡 [NAME_SEARCH] Lotes válidos: %s", lotes_validos)
                    
                    # Agregar filtro a args
                    if args is None:
                        args = []
                    args = list(args) + [('id', 'in', lotes_validos)]
                    
                    _logger.info("🟡 [NAME_SEARCH] Args actualizado: %s", args)
        
        _logger.info("🟡"*50)
        
        # Llamar al método original con args posiblemente modificado
        return super(StockLot, self).name_search(name=name, args=args, operator=operator, limit=limit)