# models/utils/hold_validator.py
# -*- coding: utf-8 -*-
"""
Validador centralizado para holds de lotes
"""
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class HoldValidator:
    """Validador de holds en lotes para entregas"""
    
    def __init__(self, env):
        self.env = env
    
    def get_customer_from_picking(self, move_line):
        """
        Obtiene el cliente del picking o sale order
        
        Args:
            move_line: stock.move.line record
            
        Returns:
            res.partner: Cliente o None
        """
        if not move_line.picking_id:
            return None
        
        # Intentar desde picking
        partner = move_line.picking_id.partner_id
        
        # Intentar desde sale order
        if move_line.move_id and move_line.move_id.sale_line_id:
            partner = move_line.move_id.sale_line_id.order_id.partner_id
        
        return partner
    
    def get_available_lots(self, product_id, location_id, customer_id):
        """
        Obtiene IDs de lotes disponibles para un cliente
        
        Args:
            product_id: int - ID del producto
            location_id: int - ID de la ubicación
            customer_id: int - ID del cliente
            
        Returns:
            list: IDs de lotes disponibles
        """
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product_id),
            ('location_id', '=', location_id),
            ('quantity', '>', 0),
        ])
        
        available_lots = []
        
        for quant in quants:
            if not quant.lot_id:
                continue
            
            # Sin hold → disponible para todos
            if not quant.x_tiene_hold:
                available_lots.append(quant.lot_id.id)
                continue
            
            # Con hold → verificar cliente
            if quant.x_hold_activo_id:
                hold_partner_id = quant.x_hold_activo_id.partner_id.id
                if hold_partner_id == customer_id:
                    available_lots.append(quant.lot_id.id)
        
        return available_lots
    
    def validate_lot_assignment(self, lot_id, location_id, customer_id):
        """
        Valida si un lote puede ser asignado a un cliente
        
        Args:
            lot_id: int - ID del lote
            location_id: int - ID de la ubicación
            customer_id: int - ID del cliente
            
        Raises:
            ValidationError: Si el lote está reservado para otro cliente
        """
        quant = self.env['stock.quant'].search([
            ('lot_id', '=', lot_id),
            ('location_id', '=', location_id),
            ('quantity', '>', 0),
            ('x_tiene_hold', '=', True),
        ], limit=1)
        
        if not quant or not quant.x_hold_activo_id:
            return  # Sin hold, permitir
        
        hold_partner = quant.x_hold_activo_id.partner_id
        
        if hold_partner.id != customer_id:
            lot = self.env['stock.lot'].browse(lot_id)
            customer = self.env['res.partner'].browse(customer_id)
            
            raise ValidationError(
                f"🔒 NO PUEDE USAR ESTE LOTE\n\n"
                f"El lote '{lot.name}' está RESERVADO para:\n"
                f"👤 {hold_partner.name}\n"
                f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n\n"
                f"❌ Esta entrega es para '{customer.name}'\n\n"
                f"Por favor, seleccione un lote disponible."
            )