# -*- coding: utf-8 -*-
# models/stock_quant.py
from odoo import models, fields, api
from odoo.exceptions import UserError
from .utils.plate_status_builder import PlateStatusBuilder
from .utils.bulk_hold_creator import BulkHoldCreator
from .utils.notification_builder import NotificationBuilder
from .utils.photo_helpers import PhotoHelper
import logging

_logger = logging.getLogger(__name__)


class StockQuant(models.Model):
    _inherit = 'stock.quant'
    
    # ==================== CAMPOS RELACIONADOS DEL LOTE ====================
    x_grosor = fields.Float(related='lot_id.x_grosor', string='Grosor', readonly=True)
    x_alto = fields.Float(related='lot_id.x_alto', string='Alto', readonly=True)
    x_ancho = fields.Float(related='lot_id.x_ancho', string='Ancho', readonly=True)
    x_bloque = fields.Char(related='lot_id.x_bloque', string='Bloque', readonly=True)
    x_tipo = fields.Selection(related='lot_id.x_tipo', string='Tipo', readonly=True)
    x_atado = fields.Char(related='lot_id.x_atado', string='Atado', readonly=True)
    x_grupo = fields.Many2many(related='lot_id.x_grupo', string='Grupo', readonly=True)
    x_pedimento = fields.Char(related='lot_id.x_pedimento', string='Pedimento', readonly=True)
    x_contenedor = fields.Char(related='lot_id.x_contenedor', string='Contenedor', readonly=True)
    x_referencia_proveedor = fields.Char(related='lot_id.x_referencia_proveedor', string='Ref. Proveedor', readonly=True)
    x_fotografia_principal = fields.Binary(related='lot_id.x_fotografia_principal', readonly=True)
    x_cantidad_fotos = fields.Integer(related='lot_id.x_cantidad_fotos', readonly=True)
    x_detalles_placa = fields.Text(related='lot_id.x_detalles_placa', string='Detalles', readonly=True)
    
    # ==================== CAMPOS DE ESTADO DE RESERVA ====================
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
    
    # ==================== CAMPOS DE HOLD MANUAL ====================
    x_hold_ids = fields.One2many(
        'stock.lot.hold',
        'quant_id',
        string='Reservas Manuales',
        help='Holds/Reservas manuales de este quant'
    )
    
    x_tiene_hold = fields.Boolean(
        string='Tiene Hold',
        compute='_compute_estado_hold',
        store=True,
        help='Indica si el lote tiene una reserva manual activa'
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
        help='Días hábiles restantes del hold'
    )
    
    # ==================== CAMPO DE ESTADO VISUAL ====================
    estado_placa = fields.Char(
        string='Estado Placa',
        compute='_compute_estado_placa',
        help='Estado visual de la placa (JSON para widget)'
    )
    
    # ==================== MÉTODOS COMPUTADOS ====================
    @api.depends('lot_id.x_detalles_placa')
    def _compute_tiene_detalles(self):
        """Verificar si la placa tiene detalles especiales"""
        for quant in self:
            quant.x_tiene_detalles = bool(
                quant.x_detalles_placa and 
                quant.x_detalles_placa.strip()
            )
    
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
            quant.x_esta_reservado = quant.reserved_quantity > 0
            quant.x_en_orden_entrega = self._check_if_in_delivery_order(quant)
    
    def _check_if_in_delivery_order(self, quant):
        """Verifica si el lote está en una orden de entrega confirmada"""
        if not quant.lot_id or not quant.x_esta_reservado:
            return False
        
        move_line = self.env['stock.move.line'].search([
            ('lot_id', '=', quant.lot_id.id),
            ('location_id', '=', quant.location_id.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('picking_id.picking_type_code', '=', 'outgoing'),
        ], limit=1)
        
        return bool(move_line)
    
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
            estados = self._build_plate_statuses(quant)
            quant.estado_placa = PlateStatusBuilder.to_json(estados)
    
    def _build_plate_statuses(self, quant):
        """Construye lista de estados de la placa"""
        estados = []
        
        # Hold manual (prioridad más alta)
        if quant.x_tiene_hold:
            estados.append(
                PlateStatusBuilder.build_hold_status(
                    quant.x_hold_para,
                    quant.x_hold_dias_restantes
                )
            )
        # Reserva del sistema (solo si no tiene hold)
        elif quant.x_esta_reservado and quant.x_en_orden_entrega:
            move_line = self._get_delivery_move_line(quant)
            if move_line:
                estados.append(
                    PlateStatusBuilder.build_delivery_status(
                        move_line.picking_id.name
                    )
                )
        
        # Detalles especiales
        if quant.x_tiene_detalles:
            estados.append(
                PlateStatusBuilder.build_details_status(quant.x_detalles_placa)
            )
        
        return estados
    
    def _get_delivery_move_line(self, quant):
        """Obtiene la move line de entrega asociada"""
        return self.env['stock.move.line'].search([
            ('lot_id', '=', quant.lot_id.id),
            ('location_id', '=', quant.location_id.id),
            ('state', 'in', ['assigned', 'partially_available']),
            ('picking_id.picking_type_code', '=', 'outgoing'),
        ], limit=1)
    
    # ==================== ACCIONES DE FOTOGRAFÍAS ====================
    def action_add_photos(self):
        """Abrir wizard para agregar fotografías al lote"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        return {
            'name': f'Agregar Fotografía al Lote {self.lot_id.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'stock.lot.image.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_lot_id': self.lot_id.id}
        }
    
    def action_view_lot_photos(self):
        """Ver las fotografías del lote"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        return PhotoHelper.build_photo_gallery_action(self.lot_id.id, self.lot_id.name)
    
    # ==================== ACCIONES DE HOLD ====================
    def action_crear_hold(self):
        """Abrir wizard para crear un hold manual en este quant"""
        self.ensure_one()
        
        if not self.lot_id:
            raise UserError('Este registro no tiene un lote asignado.')
        
        if self.x_tiene_hold:
            dias_texto = (
                f'{self.x_hold_dias_restantes} días hábiles' 
                if self.x_hold_dias_restantes != 1 
                else '1 día hábil'
            )
            raise UserError(
                f'Este lote ya tiene una reserva activa para {self.x_hold_para} '
                f'que expira en {dias_texto}.'
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
            raise UserError('Este lote no tiene una reserva activa.')
        
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
            raise UserError('Este lote no tiene una reserva activa.')
        
        self.x_hold_activo_id.action_cancelar_hold()
        
        return NotificationBuilder.build_success(
            '¡Éxito!',
            f'Reserva cancelada para el lote {self.lot_id.name}'
        )
    
    # ==================== MÉTODOS DE API ====================
    @api.model
    def get_current_user_info(self):
        """Obtener información del usuario actual"""
        return {
            'id': self.env.user.id,
            'name': self.env.user.name
        }
    
    @api.model
    def sync_cart_to_session(self, items):
        """Sincronizar carrito desde frontend a BD"""
        cart_model = self.env['shopping.cart']
        cart_model.clear_cart()
        
        for item in items:
            cart_model.add_to_cart(
                quant_id=item['id'],
                lot_id=item['lot_id'],
                product_id=item['product_id'],
                quantity=item['quantity'],
                location_name=item['location_name']
            )
        
        return {'success': True}
    
    @api.model
    def create_holds_from_cart(self, partner_id=None, project_id=None, 
                               architect_id=None, selected_lots=None, 
                               notes=None, currency_code='USD', 
                               product_prices=None):
        """Crear holds múltiples desde el carrito con información de precios"""
        creator = BulkHoldCreator(self.env)
        
        return creator.create_holds_from_cart(
            partner_id=partner_id,
            project_id=project_id,
            architect_id=architect_id,
            selected_lots=selected_lots,
            notes=notes,
            currency_code=currency_code,
            product_prices=product_prices
        )
    
    # ==================== OVERRIDE CRÍTICO - FILTRADO DE QUANTS ====================
    def _gather(self, product_id, location_id, lot_id=None, package_id=None, 
                owner_id=None, strict=False, qty=None):
        """
        Override para filtrar quants con holds antes de asignación FIFO/LIFO
        
        Solo incluye quants:
        - Sin hold, o
        - Con hold para el cliente permitido en contexto
        """
        # Llamar al método original
        quants = super(StockQuant, self)._gather(
            product_id, location_id, lot_id=lot_id, package_id=package_id,
            owner_id=owner_id, strict=strict, qty=qty
        )
        
        # Filtrar por holds si hay cliente permitido en contexto
        return self._filter_quants_by_hold(quants)
    
    def _filter_quants_by_hold(self, quants):
        """
        Filtra quants según holds del cliente permitido
        
        Args:
            quants: recordset de stock.quant
            
        Returns:
            recordset: Quants filtrados
        """
        cliente_permitido_id = self._context.get('allowed_partner_id')
        
        # Sin cliente en contexto → retornar todos
        if not cliente_permitido_id:
            return quants
        
        quants_validos = self.env['stock.quant']
        
        for quant in quants:
            if self._is_quant_available_for_customer(quant, cliente_permitido_id):
                quants_validos |= quant
        
        return quants_validos
    
    def _is_quant_available_for_customer(self, quant, customer_id):
        """
        Verifica si un quant está disponible para un cliente
        
        Args:
            quant: stock.quant record
            customer_id: int - ID del cliente
            
        Returns:
            bool: True si está disponible
        """
        # Sin hold → disponible para todos
        if not quant.x_tiene_hold:
            return True
        
        # Con hold → verificar que sea para este cliente
        if quant.x_hold_activo_id:
            hold_partner_id = quant.x_hold_activo_id.partner_id.id
            return hold_partner_id == customer_id
        
        return False