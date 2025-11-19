# -*- coding: utf-8 -*-
# models/sale_order.py
from odoo import models, api
from .utils.picking_cleaner import PickingLotCleaner
import logging
_logger = logging.getLogger(__name__)

class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

class SaleOrder(models.Model):
    _inherit = 'sale.order'
    
    def action_confirm(self):
        """
        Override para:
        1. Filtrar holds por cliente (contexto allowed_partner_id)
        2. Limpiar lotes automáticos post-confirmación
        """
        _logger.info("Confirmando órdenes: %s", self.mapped('name'))
        
        # Confirmar con contexto de cliente
        res = None
        for order in self:
            context = self._build_confirmation_context(order)
            res = super(SaleOrder, order.with_context(context)).action_confirm()
        
        # Limpiar lotes automáticos
        self._clear_auto_assigned_lots()
        
        return res
    
    def _build_confirmation_context(self, order):
        """
        Construye contexto con cliente permitido para filtrado de holds
        Args:
            order: sale.order record
        Returns:
            dict: Contexto actualizado
        """
        context = dict(self.env.context)
        if order.partner_id:
            context['allowed_partner_id'] = order.partner_id.id
        else:
            _logger.warning("Orden %s sin cliente - sin filtro de holds", order.name)
        return context
    
    def _clear_auto_assigned_lots(self):
        """Limpia lotes automáticos usando utilidad centralizada"""
        cleaner = PickingLotCleaner(self.env)
        for order in self:
            if order.picking_ids:
                cleaner.clear_pickings_lots(order.picking_ids)