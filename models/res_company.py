# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResCompany(models.Model):
    _inherit = 'res.company'

    x_sale_bank_info_ids = fields.One2many(
        'res.company.bank.info',
        'company_id',
        string='Datos Bancarios Comerciales'
    )

    x_payment_receipt_emails = fields.Char(
        string='Correos para recepción de comprobantes',
        help='Separar múltiples correos con coma'
    )

    @api.model
    def _load_default_sale_bank_info(self):
        """
        Carga los datos bancarios actuales SOLO si la compañía aún no tiene registros.
        Esto permite que el módulo se actualice sin duplicar información.
        """
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