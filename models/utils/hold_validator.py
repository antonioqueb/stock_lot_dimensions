# -*- coding: utf-8 -*-
"""
Validador centralizado para holds de lotes con soporte multi-compañía
"""
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class HoldValidator:
    """Validador de holds en lotes para entregas con soporte multi-compañía"""
    
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
    
    def get_available_lots(self, product_id, location_id, customer_id, company_id=None):
        """
        Obtiene IDs de lotes disponibles para un cliente en una compañía específica
        
        Args:
            product_id: int - ID del producto
            location_id: int - ID de la ubicación
            customer_id: int - ID del cliente
            company_id: int - ID de la compañía (opcional, usa la actual por defecto)
            
        Returns:
            list: IDs de lotes disponibles
        """
        if company_id is None:
            company_id = self.env.company.id
        
        # Buscar quants de la compañía especificada
        quants = self.env['stock.quant'].search([
            ('product_id', '=', product_id),
            ('location_id', '=', location_id),
            ('quantity', '>', 0),
            ('company_id', '=', company_id),
        ])
        
        available_lots = []
        
        for quant in quants:
            if not quant.lot_id:
                continue
            
            # Sin hold → disponible para todos
            if not quant.x_tiene_hold:
                available_lots.append(quant.lot_id.id)
                continue
            
            # Con hold → verificar compañía y cliente
            if quant.x_hold_activo_id:
                # Verificar que sea de la misma compañía
                if quant.x_hold_activo_id.company_id.id == company_id:
                    # Hold de la misma compañía → verificar cliente
                    hold_partner_id = quant.x_hold_activo_id.partner_id.id
                    if hold_partner_id == customer_id:
                        available_lots.append(quant.lot_id.id)
                else:
                    # Hold de otra compañía → lote disponible
                    available_lots.append(quant.lot_id.id)
                    _logger.debug(
                        "Lote %s disponible: hold es de otra compañía (Hold: %s, Buscado: %s)",
                        quant.lot_id.name,
                        quant.x_hold_activo_id.company_id.name,
                        self.env['res.company'].browse(company_id).name
                    )
        
        _logger.debug(
            "Lotes disponibles para producto=%s, ubicación=%s, cliente=%s, compañía=%s: %d lotes",
            product_id,
            location_id,
            customer_id,
            company_id,
            len(available_lots)
        )
        
        return available_lots
    
    def validate_lot_assignment(self, lot_id, location_id, customer_id, company_id=None):
        """
        Valida si un lote puede ser asignado a un cliente en una compañía específica
        
        Args:
            lot_id: int - ID del lote
            location_id: int - ID de la ubicación
            customer_id: int - ID del cliente
            company_id: int - ID de la compañía (opcional, usa la actual por defecto)
            
        Raises:
            ValidationError: Si el lote está reservado para otro cliente en la misma compañía
        """
        if company_id is None:
            company_id = self.env.company.id
        
        # Buscar quant con hold en la compañía especificada
        quant = self.env['stock.quant'].search([
            ('lot_id', '=', lot_id),
            ('location_id', '=', location_id),
            ('quantity', '>', 0),
            ('company_id', '=', company_id),
            ('x_tiene_hold', '=', True),
        ], limit=1)
        
        if not quant or not quant.x_hold_activo_id:
            return  # Sin hold, permitir
        
        # Verificar que el hold sea de la misma compañía
        if quant.x_hold_activo_id.company_id.id != company_id:
            _logger.debug(
                "Hold de lote %s es de otra compañía, permitiendo asignación",
                quant.lot_id.name
            )
            return  # Hold de otra compañía no aplica
        
        # Hold de la misma compañía → verificar cliente
        hold_partner = quant.x_hold_activo_id.partner_id
        
        if hold_partner.id != customer_id:
            # 🔑 Cargar objetos completos ANTES de construir el mensaje
            lot = self.env['stock.lot'].browse(lot_id)
            customer = self.env['res.partner'].browse(customer_id)
            company = self.env['res.company'].browse(company_id)
            
            error_msg = (
                f"🔒 NO PUEDE USAR ESTE LOTE\n\n"
                f"El lote '{lot.name}' está RESERVADO para:\n"
                f"👤 {hold_partner.name}\n"
                f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n"
                f"🏢 Compañía: {company.name}\n\n"
                f"❌ Esta entrega es para '{customer.name}'\n\n"
                f"Por favor, seleccione un lote disponible."
            )
            
            _logger.warning(
                "Validación de hold fallida: Lote=%s, Hold para=%s, "
                "Intentando asignar a=%s, Compañía=%s",
                lot.name,
                hold_partner.name,
                customer.name,
                company.name
            )
            
            raise ValidationError(error_msg)
        
        # Validación exitosa - obtener nombre del cliente para log
        customer = self.env['res.partner'].browse(customer_id)
        _logger.debug(
            "Validación de hold exitosa: Lote %s para cliente %s en compañía %s",
            quant.lot_id.name,
            customer.name,
            company_id
        )