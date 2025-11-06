# -*- coding: utf-8 -*-
# models/stock_picking.py
from odoo import models, api
from odoo.exceptions import UserError
from .utils.picking_cleaner import PickingLotCleaner
from .utils.hold_validator import HoldValidator
import logging

_logger = logging.getLogger(__name__)


class StockPicking(models.Model):
    _inherit = 'stock.picking'
    
    def action_assign(self):
        """
        Override para filtrar quants con hold al reservar
        Añade el contexto de cliente permitido para filtrado FIFO/LIFO
        """
        for picking in self:
            if self._should_filter_by_hold(picking):
                context = self._build_hold_context(picking)
                self = self.with_context(**context)
        
        return super(StockPicking, self).action_assign()
    
    def _action_assign(self):
        """
        Override para limpiar lotes automáticos después de la asignación
        Solo limpia lotes de pickings que vienen de órdenes de venta
        """
        # Ejecutar asignación normal
        result = super(StockPicking, self)._action_assign()
        
        # Limpiar lotes automáticos de pickings de sale orders
        self._clear_auto_assigned_lots_from_sales()
        
        return result
    
    def button_validate(self):
        """
        Validar holds antes de validar el picking
        Verifica que los lotes asignados no tengan holds de otros clientes
        """
        self._validate_holds_before_transfer()
        
        return super(StockPicking, self).button_validate()
    
    # ==================== MÉTODOS AUXILIARES ====================
    
    def _should_filter_by_hold(self, picking):
        """
        Determina si se debe filtrar por holds
        
        Args:
            picking: stock.picking record
            
        Returns:
            bool: True si se debe filtrar
        """
        return (
            picking.picking_type_code == 'outgoing' and 
            picking.partner_id
        )
    
    def _build_hold_context(self, picking):
        """
        Construye contexto con información de cliente y empresa
        
        Args:
            picking: stock.picking record
            
        Returns:
            dict: Contexto actualizado
        """
        company_id = picking.company_id.id if picking.company_id else self.env.company.id
        
        return {
            'allowed_partner_id': picking.partner_id.id,
            'company_id': company_id
        }
    
    def _clear_auto_assigned_lots_from_sales(self):
        """Limpia lotes automáticos solo de pickings que vienen de sale orders"""
        cleaner = PickingLotCleaner(self.env)
        
        # Filtrar solo pickings de sale orders
        sale_pickings = self.filtered(lambda p: p.sale_id)
        
        if sale_pickings:
            _logger.info(
                "Limpiando lotes automáticos de %d pickings de sale orders: %s",
                len(sale_pickings),
                sale_pickings.mapped('name')
            )
            cleaner.clear_pickings_lots(sale_pickings)
    
    def _validate_holds_before_transfer(self):
        """
        Valida que todos los lotes asignados no tengan holds de otros clientes
        
        Raises:
            UserError: Si algún lote está reservado para otro cliente
        """
        validator = HoldValidator(self.env)
        
        for picking in self:
            # Solo validar pickings de salida
            if picking.picking_type_code != 'outgoing':
                continue
            
            company_id = picking.company_id.id if picking.company_id else self.env.company.id
            
            self._validate_picking_move_lines(picking, validator, company_id)
    
    def _validate_picking_move_lines(self, picking, validator, company_id):
        """
        Valida las move lines de un picking específico
        
        Args:
            picking: stock.picking record
            validator: HoldValidator instance
            company_id: int - ID de la empresa
            
        Raises:
            UserError: Si algún lote tiene hold de otro cliente
        """
        for move_line in picking.move_line_ids:
            if not move_line.lot_id:
                continue
            
            # Buscar quant con hold activo
            quant = self._find_quant_with_hold(
                move_line.lot_id.id,
                move_line.location_id.id,
                company_id
            )
            
            if quant and quant.x_hold_activo_id:
                self._check_hold_customer_match(picking, move_line, quant)
    
    def _find_quant_with_hold(self, lot_id, location_id, company_id):
        """
        Busca quant con hold activo
        
        Args:
            lot_id: int - ID del lote
            location_id: int - ID de la ubicación
            company_id: int - ID de la empresa
            
        Returns:
            stock.quant: Quant con hold o None
        """
        return self.env['stock.quant'].search([
            ('lot_id', '=', lot_id),
            ('location_id', '=', location_id),
            ('company_id', '=', company_id),
            ('x_tiene_hold', '=', True),
        ], limit=1)
    
    def _check_hold_customer_match(self, picking, move_line, quant):
        """
        Verifica que el hold sea para el cliente correcto
        
        Args:
            picking: stock.picking record
            move_line: stock.move.line record
            quant: stock.quant record con hold
            
        Raises:
            UserError: Si el hold es para otro cliente
        """
        if picking.partner_id != quant.x_hold_activo_id.partner_id:
            raise UserError(
                f"🔒 NO PUEDE VALIDAR ESTA ENTREGA\n\n"
                f"El lote '{move_line.lot_id.name}' está RESERVADO para:\n"
                f"👤 {quant.x_hold_para}\n"
                f"📅 Hasta: {quant.x_hold_expira.strftime('%d/%m/%Y %H:%M')}\n"
                f"⏱️ Días restantes: {quant.x_hold_dias_restantes}\n\n"
                f"❌ Esta entrega es para '{picking.partner_id.name}'"
            )