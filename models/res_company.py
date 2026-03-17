# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    x_payment_receipt_emails = fields.Char(
        string='Correos para recepción de comprobantes',
        help='Separar múltiples correos con coma'
    )

    x_sale_bank_info_ids = fields.One2many(
        'res.company.bank.info',
        'company_id',
        string='Datos Bancarios Comerciales'
    )

    x_sale_bank_info_count = fields.Integer(
        string='Datos Bancarios',
        compute='_compute_x_sale_bank_info_count'
    )

    def _compute_x_sale_bank_info_count(self):
        for company in self:
            company.x_sale_bank_info_count = len(company.x_sale_bank_info_ids)

    def action_open_sale_bank_info(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Datos Bancarios Comerciales',
            'res_model': 'res.company.bank.info',
            'view_mode': 'list,form',
            'domain': [('company_id', '=', self.id)],
            'context': {
                'default_company_id': self.id,
            },
            'target': 'current',
        }

    @api.model
    def _load_default_sale_bank_info(self):
        companies = self.search([])
        usd = self.env.ref('base.USD', raise_if_not_found=False)
        mxn = self.env.ref('base.MXN', raise_if_not_found=False)

        default_rows = [
            {
                'sequence': 10,
                'name': 'Banorte USD',
                'bank_name': 'Banorte',
                'currency_id': usd.id if usd else False,
                'account_holder': 'Recubrimientos STO SA de CV',
                'account_number': '1097074150',
                'clabe': '072580010970741500',
                'swift': 'MENOMXMTXXX',
                'branch': '1924 Paseo Santa Catarina',
                'active': True,
            },
            {
                'sequence': 20,
                'name': 'Banorte MXN',
                'bank_name': 'Banorte',
                'currency_id': mxn.id if mxn else False,
                'account_holder': 'Recubrimientos STO SA de CV',
                'account_number': '1060415841',
                'clabe': '072580010604158414',
                'swift': False,
                'branch': '1924 Paseo Santa Catarina',
                'active': True,
            },
        ]

        for company in companies:
            if not company.x_payment_receipt_emails:
                company.x_payment_receipt_emails = 'norma@somgroup.com, clara@somgroup.com'

            if company.x_sale_bank_info_ids:
                continue

            for vals in default_rows:
                if not vals.get('currency_id'):
                    continue
                self.env['res.company.bank.info'].create({
                    **vals,
                    'company_id': company.id,
                })