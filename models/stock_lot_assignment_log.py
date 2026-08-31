# -*- coding: utf-8 -*-
# models/stock_lot_assignment_log.py
"""
Bitácora de ASIGNACIÓN de placas a documentos comerciales.

Por qué existe: `sale.order.line.lot_ids` es un many2many sin tracking. Cuando
una placa desaparecía de un pedido, en la base no quedaba absolutamente nada
—ni en el chatter, ni en tracking_value— y la única pista era el log del
servidor ("[STONE LINE WRITE] lot_ids EN vals: ..."), que se rota y no dice el
NOMBRE del lote. Preguntas del tipo "¿por qué V/091 se quedó sin material y
quién lo quitó?" eran imposibles de responder.

Cada movimiento de placa hacia/desde un documento deja aquí un renglón con
QUIÉN, CUÁNDO, DE QUÉ DOCUMENTO y POR QUÉ (el motivo lo pone el flujo que
dispara el cambio vía el contexto `som_lot_log_reason`; sin él se asume
selección manual).

El modelo vive en stock_lot_dimensions —y no en sale_stone_selection, que es
quien escribe— porque el Inventario Visual (inventory_visual_enhanced) es
quien lo LEE y ambos dependen de este módulo.
"""
from odoo import models, fields, api

import logging

_logger = logging.getLogger(__name__)


class StockLotAssignmentLog(models.Model):
    _name = 'stock.lot.assignment.log'
    _description = 'Bitácora de Asignación de Placas'
    _order = 'date desc, id desc'
    _rec_name = 'lot_id'

    lot_id = fields.Many2one(
        'stock.lot',
        string='Placa',
        required=True,
        index=True,
        ondelete='cascade',
    )
    # Multiempresa: la del DOCUMENTO que asigna (la escribe _som_log_lots);
    # si no viene, la de la placa y, en último caso, la activa. Almacenado
    # para la regla de registro; los renglones históricos se rellenan en
    # el -u con este cómputo.
    company_id = fields.Many2one(
        'res.company',
        string='Compañía',
        compute='_compute_company_id',
        store=True,
        readonly=False,
        index=True,
    )
    action = fields.Selection(
        [('assign', 'Asignada'), ('unassign', 'Desasignada')],
        string='Acción',
        required=True,
        index=True,
    )
    date = fields.Datetime(
        string='Fecha',
        required=True,
        index=True,
        default=fields.Datetime.now,
    )
    user_id = fields.Many2one(
        'res.users',
        string='Usuario',
        index=True,
        help='Quién ejecutó el cambio (el usuario REAL, no el sudo).',
    )
    document_model = fields.Char(string='Modelo del Documento', index=True)
    document_id = fields.Integer(string='ID del Documento', index=True)
    document_name = fields.Char(string='Documento', index=True)
    document_line_id = fields.Integer(string='ID de la Línea')
    product_id = fields.Many2one('product.product', string='Producto')
    partner_id = fields.Many2one('res.partner', string='Cliente')
    salesperson_id = fields.Many2one('res.users', string='Vendedor del Documento')
    reason = fields.Char(
        string='Motivo',
        help='Qué flujo disparó el cambio: selección manual, borrado de '
             'línea, limpieza al confirmar, conversión de cotización…',
    )
    note = fields.Char(string='Detalle')

    # Motivo por defecto cuando nadie declara uno: neutral a propósito. Los
    # flujos AUTOMÁTICOS que quitan placas (limpieza al confirmar, borrado de
    # línea, liberación al recibir, STONE SYNC desde la entrega) se etiquetan
    # solos pasando `som_lot_log_reason` en el contexto; lo que cae aquí es
    # una edición hecha desde el documento.
    DEFAULT_REASON = 'Cambio de selección en el documento'

    @api.depends('lot_id.company_id')
    def _compute_company_id(self):
        for rec in self:
            if rec.company_id:
                continue
            rec.company_id = rec.lot_id.company_id or self.env.company

    @api.model
    def _som_current_reason(self):
        return self.env.context.get('som_lot_log_reason') or self.DEFAULT_REASON

    @api.model
    def _som_log_lots(self, lots, action, document=None, line=None,
                      reason=None, note=None, partner=None,
                      salesperson=None, product=None):
        """Registra un lote (o varios) entrando o saliendo de un documento.

        Nunca revienta el flujo que la llama: una bitácora que tumba una venta
        es peor que no tener bitácora. Se escribe con sudo() porque el
        vendedor no tiene permiso de escritura sobre el modelo, pero el
        `user_id` guardado es SIEMPRE el usuario real de la sesión.
        """
        if not lots:
            return self.browse()

        try:
            vals_list = []
            base = {
                'action': action,
                'date': fields.Datetime.now(),
                'user_id': self.env.user.id,
                'reason': reason or self._som_current_reason(),
                'note': note or False,
                'partner_id': partner.id if partner else False,
                'salesperson_id': salesperson.id if salesperson else False,
            }
            if document is not None and document:
                base.update({
                    'document_model': document._name,
                    'document_id': document.id,
                    'document_name': document.display_name or '',
                })
                doc_company = (
                    document.company_id
                    if 'company_id' in document._fields else False)
                if doc_company:
                    base['company_id'] = doc_company.id
            if line is not None and line:
                base['document_line_id'] = line.id
            if product:
                base['product_id'] = product.id

            for lot in lots:
                vals = dict(base)
                vals['lot_id'] = lot.id
                if not vals.get('product_id') and lot.product_id:
                    vals['product_id'] = lot.product_id.id
                if not vals.get('company_id'):
                    vals['company_id'] = (
                        lot.company_id.id or self.env.company.id)
                vals_list.append(vals)

            return self.sudo().create(vals_list)
        except Exception:
            _logger.exception(
                '[LOT LOG] No se pudo registrar la bitácora de asignación '
                '(lotes=%s, acción=%s).', lots.ids if lots else [], action)
            return self.browse()

    @api.model
    def som_get_lot_trail(self, lot_id, limit=200):
        """Bitácora de una placa, lista para pintar. La consume el historial
        del lote en el Inventario Visual."""
        records = self.sudo().search(
            [('lot_id', '=', int(lot_id))], limit=limit)
        return [{
            'id': rec.id,
            'action': rec.action,
            'action_label': 'Asignada' if rec.action == 'assign' else 'Desasignada',
            'date_obj': rec.date,
            'usuario': rec.user_id.name or 'Sistema',
            'documento': rec.document_name or '',
            'document_model': rec.document_model or '',
            'document_id': rec.document_id or 0,
            'cliente': rec.partner_id.name or '',
            'vendedor': rec.salesperson_id.name or '',
            'motivo': rec.reason or '',
            'detalle': rec.note or '',
        } for rec in records]
