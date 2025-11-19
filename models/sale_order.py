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
        
        # 🔑 CRÍTICO: Ejecutar super() en el recordset completo PRIMERO
        # Construir contexto agregado con todos los clientes
        all_partner_ids = self.mapped('partner_id.id')
        context = dict(self.env.context)
        
        if all_partner_ids:
            # Si hay un solo cliente, usar allowed_partner_id
            if len(all_partner_ids) == 1:
                context['allowed_partner_id'] = all_partner_ids[0]
            # Si hay múltiples clientes, usar lista (para filtrado más complejo)
            else:
                context['allowed_partner_ids'] = all_partner_ids
        
        # Ejecutar confirmación con contexto
        res = super(SaleOrder, self.with_context(**context)).action_confirm()
        
        # Limpiar lotes automáticos DESPUÉS de confirmar
        self._clear_auto_assigned_lots()
        
        return res
    
    def _clear_auto_assigned_lots(self):
        """Limpia lotes automáticos usando utilidad centralizada"""
        cleaner = PickingLotCleaner(self.env)
        for order in self:
            if order.picking_ids:
                cleaner.clear_pickings_lots(order.picking_ids)