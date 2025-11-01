# -*- coding: utf-8 -*-
from odoo import models, fields, api
import json
import logging

_logger = logging.getLogger(__name__)

class StockQuant(models.Model):
    _inherit = 'stock.quant'

    # Campos relacionados del lote
    x_grosor = fields.Float(related='lot_id.x_grosor', string='Grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', string='Alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', string='Ancho', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', string='Bloque', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', string='Atado', readonly=True)
    x_formato = fields.Selection(related='lot_id.x_formato', string='Formato', readonly=True)
    x_fotografia_principal = fields.Binary(related='lot_id.x_fotografia_principal', readonly=True)
    x_cantidad_fotos = fields.Integer(related='lot_id.x_cantidad_fotos', readonly=True)
    x_detalles_placa = fields.Text(related='lot_id.x_detalles_placa', string='Detalles', readonly=True)
    
    # Campos computados de estado
    x_esta_reservado = fields.Boolean(
        string='Reservado (Sistema)',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está reservado por el sistema de entregas'
    )
    
    x_en_orden_entrega = fields.Boolean(
        string='En Orden de Entrega',
        compute='_compute_estado_reserva',
        store=True,
        help='Indica si el lote está en una orden de entrega confirmada'
    )
    
    x_tiene_detalles = fields.Boolean(
        string='Tiene Detalles',
        compute='_compute_tiene_detalles',
        store=True,
        help='Indica si la placa tiene detalles especiales registrados'
    )
    
    # CAMPOS PARA HOLD MANUAL
    x_tiene_hold = fields.Boolean(
        string='Tiene Hold',
        compute='_compute_estado_hold',
        store=True,
        help='Indica si el lote tiene una reserva manual activa'
    )
    
    x_hold_ids = fields.One2many(
        'stock.lot.hold',
        'quant_id',
        string='Reservas Manuales',
        help='Holds/Reservas manuales de este quant'
    )
    
    x_hold_activo_id = fields.Many2one(
        'stock.lot.hold',
        string='Hold Activo',
        compute='_compute_estado_hold',
        store=True,
        help='Hold activo actualmente en este quant'
    )
    
    x_hold_para = fields.Char(
        string='Reservado Para',
        compute='_compute_estado_hold',
        store=True,
        help='Cliente para quien está reservado'
    )
    
    x_hold_expira = fields.Datetime(
        string='Expira',
        compute='_compute_estado_hold',
        store=True,
        help='Fecha de expiración del hold'
    )
    
    x_hold_dias_restantes = fields.Integer(
        string='Días Restantes',
        compute='_compute_estado_hold',
        help='Días restantes del hold'
    )
    
    # Campo de estado visual combinado
    estado_placa = fields.Char(
        string='Estado Placa',
        compute='_compute_estado_placa',
        help='Estado visual de la placa (JSON para widget)'
    )

    @api.depends('lot_id.x_detalles_placa')
    def _compute_tiene_detalles(self):
        """Verificar si la placa tiene detalles especiales"""
        for quant in self:
            quant.x_tiene_detalles = bool(quant.x_detalles_placa and quant.x_detalles_placa.strip())

    @api.depends('x_hold_ids.estado', 'x_hold_ids.fecha_expiracion')
    def _compute_estado_hold(self):
        """Computar el estado del hold manual"""
        for quant in self:
            hold_activo = quant.x_hold_ids.filtered(lambda h: h.estado == 'activo')
            if hold_activo:
                # Tomar el más reciente si hay múltiples
                hold_activo = hold_activo[0]
                quant.x_tiene_hold = True
                quant.x_hold_activo_id = hold_activo.id
                quant.x_hold_para = hold_activo.partner_id.name
                quant.x_hold_expira = hold_activo.fecha_expiracion
                quant.x_hold_dias_restantes = hold_activo.dias_restantes
            else:
                quant.x_tiene_hold = False
                quant.x_hold_activo_id = False
                quant.x_hold_para = False
                quant.x_hold_expira = False
                quant.x_hold_dias_restantes = 0

    @api.depends('reserved_quantity', 'quantity', 'lot_id')
    def _compute_estado_reserva(self):
        """Computar si el lote está reservado por el sistema de entregas"""
        for quant in self:
            # Solo verificar si hay cantidad reservada por el sistema
            quant.x_esta_reservado = quant.reserved_quantity > 0
            
            # Verificar si está en una orden de entrega confirmada
            quant.x_en_orden_entrega = False
            
            if quant.lot_id and quant.x_esta_reservado:
                # Buscar move lines con este lote en estado asignado
                move_lines = self.env['stock.move.line'].search([
                    ('lot_id', '=', quant.lot_id.id),
                    ('location_id', '=', quant.location_id.id),
                    ('state', 'in', ['assigned', 'partially_available']),
                    ('picking_id.picking_type_code', '=', 'outgoing'),
                ], limit=1)
                
                if move_lines:
                    quant.x_en_orden_entrega = True

    @api.depends(
        'x_esta_reservado',
        'x_en_orden_entrega', 
        'x_tiene_detalles',
        'x_detalles_placa',
        'x_tiene_hold',
        'x_hold_para',
        'x_hold_dias_restantes'
    )
    def _compute_estado_placa(self):
        """Generar JSON con los estados para el widget visual"""
        for quant in self:
            estados = []
            
            # HOLD MANUAL (prioridad más alta)
            if quant.x_tiene_hold:
                estados.append({
                    'type': 'hold',
                    'icon': '🔒',
                    'label': f'HOLD para {quant.x_hold_para}',
                    'detail': f'Expira en {quant.x_hold_dias_restantes} días',
                    'class': 'text-warning' if quant.x_hold_dias_restantes <= 3 else 'text-info'
                })
            
            # RESERVA DEL SISTEMA (solo si no tiene hold manual)
            elif quant.x_esta_reservado and quant.x_en_orden_entrega:
                # Obtener el documento de referencia
                move_line = self.env['stock.move.line'].search([
                    ('lot_id', '=', quant.lot_id.id),
                    ('location_id', '=', quant.location_id.id),
                    ('state', 'in', ['assigned', 'partially_available']),
                    ('picking_id.picking_type_code', '=', 'outgoing'),
                ], limit=1)
                
                if move_line:
                    estados.append({
                        'type': 'delivery',
                        'icon': '📦',
                        'label': 'En Orden de Entrega',
                        'detail': f'Doc: {move_line.picking_id.name}',
                        'class': 'text-primary'
                    })
            
            # DETALLES ESPECIALES
            if quant.x_tiene_detalles:
                detalles_cortos = quant.x_detalles_placa[:30] + '...' if len(quant.x_detalles_placa) > 30 else quant.x_detalles_placa
                estados.append({
                    'type': 'details',
                    'icon': '⚠️',
                    'label': 'Detalles Especiales',
                    'detail': detalles_cortos,
                    'class': 'text-danger'
                })
            
            quant.estado_placa = json.dumps(estados) if estados else False

    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        if not self.lot_id:
            raise models.UserError('Este registro no tiene un lote asignado.')
        
        return {
            'name': f'Agregar Fotografía al Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lot_id': self.lot_id.id,
            }
        }

    def action_view_lot_photos(self):
        """Ver las fotografías del lote"""
        self.ensure_one()
        if not self.lot_id:
            raise models.UserError('Este registro no tiene un lote asignado.')
        
        return {
            'name': f'Fotografías del Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image',
            'view_mode': 'tree,form',
            'domain': [('lot_id', '=', self.lot_id.id)],
            'context': {
                'default_lot_id': self.lot_id.id,
            }
        }

    # ACCIONES PARA HOLD
    def action_crear_hold(self):
        """Abrir wizard para crear un hold manual en este quant"""
        self.ensure_one()
        if not self.lot_id:
            raise models.UserError('Este registro no tiene un lote asignado.')
        
        # Verificar si ya tiene hold activo
        if self.x_tiene_hold:
            raise models.UserError(
                f'Este lote ya tiene una reserva activa para {self.x_hold_para} '
                f'que expira en {self.x_hold_dias_restantes} días.'
            )
        
        return {
            'name': f'Reservar Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_quant_id': self.id,
                'default_lot_id': self.lot_id.id,
            }
        }

    def action_ver_hold(self):
        """Ver detalles del hold activo"""
        self.ensure_one()
        if not self.x_hold_activo_id:
            raise models.UserError('Este lote no tiene una reserva activa.')
        
        return {
            'name': f'Reserva del Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.hold',
            'view_mode': 'form',
            'res_id': self.x_hold_activo_id.id,
            'target': 'new',
        }

    def action_cancelar_hold(self):
        """Cancelar el hold activo"""
        self.ensure_one()
        if not self.x_hold_activo_id:
            raise models.UserError('Este lote no tiene una reserva activa.')
        
        self.x_hold_activo_id.action_cancelar_hold()
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': '¡Éxito!',
                'message': f'Reserva cancelada para el lote {self.lot_id.name}',
                'type': 'success',
                'sticky': False,
            }
        }

    def _gather(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False, qty=None):
        """
        🔑 OVERRIDE CRÍTICO: Este método es llamado por Odoo para SELECCIONAR qué quants usar.
        
        Aquí es donde debemos filtrar los lotes con holds ANTES de que sean asignados.
        
        Este método se ejecuta ANTES de _get_available_quantity y es el lugar correcto
        para filtrar quants basándonos en holds.
        
        Parámetros Odoo 18:
        - qty: Cantidad requerida (nuevo en Odoo 18)
        """
        _logger.info("🟢" * 50)
        _logger.info("🟢 [_GATHER] Iniciando _gather")
        _logger.info("🟢 [_GATHER] Product: %s", product_id.name if product_id else 'N/A')
        _logger.info("🟢 [_GATHER] Location: %s", location_id.name if location_id else 'N/A')
        _logger.info("🟢 [_GATHER] Lot: %s", lot_id.name if lot_id else 'N/A')
        _logger.info("🟢 [_GATHER] Qty: %s", qty)
        
        # Llamar al método original con todos los parámetros
        quants = super(StockQuant, self)._gather(
            product_id, location_id, lot_id=lot_id, package_id=package_id, 
            owner_id=owner_id, strict=strict, qty=qty
        )
        
        _logger.info("🟢 [_GATHER] Quants originales encontrados: %s", len(quants))
        
        # Si no hay cliente permitido en contexto, retornar todos los quants
        cliente_permitido_id = self._context.get('allowed_partner_id')
        
        if not cliente_permitido_id:
            _logger.info("🟢 [_GATHER] ⚠️ No hay allowed_partner_id en contexto")
            _logger.info("🟢 [_GATHER] Retornando todos los quants sin filtrar")
            _logger.info("🟢" * 50)
            return quants
        
        _logger.info("🟢 [_GATHER] ✅ Cliente permitido en contexto: ID %s", cliente_permitido_id)
        
        # Filtrar quants que tienen hold para OTRO cliente
        quants_validos = self.env['stock.quant']
        
        for quant in quants:
            lot_name = quant.lot_id.name if quant.lot_id else 'Sin lote'
            tiene_hold = quant.x_tiene_hold
            
            _logger.info("🟢 [_GATHER] ─────────────────────────────────────")
            _logger.info("🟢 [_GATHER] Analizando Quant ID: %s, Lote: %s", quant.id, lot_name)
            _logger.info("🟢 [_GATHER] Cantidad: %.2f, Tiene hold: %s", quant.quantity, tiene_hold)
            
            # Si no tiene hold, es válido
            if not tiene_hold:
                _logger.info("🟢 [_GATHER] ✅ SIN HOLD - Agregando a lista válida")
                quants_validos |= quant
                continue
            
            # Si tiene hold, verificar que sea para este cliente
            if quant.x_hold_activo_id:
                hold_partner_id = quant.x_hold_activo_id.partner_id.id
                hold_partner_name = quant.x_hold_activo_id.partner_id.name
                
                _logger.info("🟢 [_GATHER] Hold activo encontrado:")
                _logger.info("🟢 [_GATHER]   - Partner del hold: %s (ID: %s)", hold_partner_name, hold_partner_id)
                _logger.info("🟢 [_GATHER]   - Partner permitido: ID %s", cliente_permitido_id)
                
                if hold_partner_id == cliente_permitido_id:
                    _logger.info("🟢 [_GATHER] ✅ HOLD PARA CLIENTE PERMITIDO - Agregando a lista válida")
                    quants_validos |= quant
                else:
                    _logger.warning("🟢 [_GATHER] ❌ HOLD PARA OTRO CLIENTE - NO agregando")
                    _logger.warning("🟢 [_GATHER]    Este quant NO debe ser usado por FIFO/LIFO")
            else:
                _logger.warning("🟢 [_GATHER] ⚠️ Tiene hold pero sin x_hold_activo_id - NO agregando")
        
        _logger.info("🟢 [_GATHER] ═════════════════════════════════════════")
        _logger.info("🟢 [_GATHER] RESUMEN:")
        _logger.info("🟢 [_GATHER] Quants originales: %s", len(quants))
        _logger.info("🟢 [_GATHER] Quants válidos después del filtro: %s", len(quants_validos))
        _logger.info("🟢 [_GATHER] _gather() FINALIZADO")
        _logger.info("🟢" * 50)
        
        return quants_validos