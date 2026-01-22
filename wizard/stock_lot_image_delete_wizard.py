# -*- coding: utf-8 -*-
from odoo import models, fields, api
from odoo.exceptions import UserError
from ..models.utils.notification_builder import NotificationBuilder

class StockLotImageDeleteWizard(models.TransientModel):
    _name = 'stock.lot.image.delete.wizard'
    _description = 'Eliminación Masiva de Fotos de Lotes'

    confirm_deletion = fields.Boolean(
        string='Confirmo que deseo eliminar TODAS las fotografías',
        default=False,
        help='Debe marcar esta casilla para proceder. Esta acción no se puede deshacer.'
    )
    
    total_images = fields.Integer(
        string='Total de Fotos a Eliminar',
        compute='_compute_total_images'
    )

    @api.depends('confirm_deletion') # Trigger dummy para calcular al abrir
    def _compute_total_images(self):
        count = self.env['stock.lot.image'].search_count([])
        for record in self:
            record.total_images = count

    def action_delete_all_images(self):
        self.ensure_one()
        
        if not self.confirm_deletion:
            raise UserError("Debe confirmar la acción marcando la casilla de verificación.")

        # Buscar todas las imágenes
        images = self.env['stock.lot.image'].search([])
        count = len(images)
        
        if count == 0:
            raise UserError("No hay fotografías para eliminar.")

        # Eliminar registros (Odoo se encarga de borrar los attachments binarios asociados)
        images.unlink()
        
        return NotificationBuilder.build_success(
            'Limpieza Completada',
            f'Se han eliminado correctamente {count} fotografías del sistema.',
            sticky=True
        )