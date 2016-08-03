# -*- coding: utf-8 -*-

# This file is part of sale_pos module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
from decimal import Decimal
import datetime
from trytond.model import ModelSQL, Workflow, fields, ModelView
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction
from trytond.pyson import Bool, Eval, Or, If
from trytond.wizard import (Wizard, StateView, StateAction, StateTransition,
    Button)
from trytond.modules.company import CompanyReport
from trytond.report import Report
from lxml import etree
import base64
import xmlrpclib
import re
from xml.dom.minidom import parse, parseString
import time
from trytond.rpc import RPC
import os
from trytond import backend

_ZERO = Decimal('0.0')

_TYPE = [
    ('service', 'Servicio'),
]

__all__ = ['Periferic', 'Service', 'ServiceLine', 'HistoryLine',
            'ServiceReport']

_STATES = {
    'readonly': Eval('state') == 'delivered',
}
_DEPENDS = ['state']

class Periferic(ModelSQL, ModelView):
    'Periferic'
    __name__ = 'service.periferic'
    name = fields.Char('Periferic', size=None, required=True, translate=True)

    @classmethod
    def __setup__(cls):
        super(Periferic, cls).__setup__()
        t = cls.__table__()

    @classmethod
    def __register__(cls, module_name):
        TableHandler = backend.get('TableHandler')
        cursor = Transaction().cursor
        table = TableHandler(cursor, cls, module_name)

        super(Periferic, cls).__register__(module_name)

        if table.column_exist('code'):
            table.drop_column('code')


class Service(Workflow, ModelSQL, ModelView):
    'Service'
    __name__ = 'service.service'
    __history = True
    company = fields.Many2One('company.company', 'Company', required=True,
        readonly=True, select=True, domain=[
            ('id', If(Eval('context', {}).contains('company'), '=', '!='),
                Eval('context', {}).get('company', -1)),
            ],
        depends=_DEPENDS)
    party = fields.Many2One('party.party', 'Party', states=_STATES)
    number_service = fields.Char('No. Comprobante', readonly=True)
    type = fields.Selection(_TYPE, 'Type', select=True, states=_STATES)
    total = fields.Function(fields.Numeric('Total'), 'get_amount')

    entry_date = fields.Date('Entry Date', states=_STATES,
        domain=[('entry_date', '<', Eval('delivery_date', None))],
        depends=['delivery_date'])
    delivery_date = fields.Date('Estimated Delivery Date', states=_STATES,
        domain=[('delivery_date', '>', Eval('entry_date', None))],
        depends=['entry_date'])
    technical = fields.Many2One('company.employee', 'Technical', states=_STATES)
    garanty = fields.Boolean('Garanty', help="Income Garanty", states=_STATES)
    invoice_date = fields.Date('Invoice Date', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    invoice_number = fields.Char('Invoice number', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    case_number = fields.Char('Case number', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    send_date = fields.Date('Send Date', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    remission = fields.Char('No. guide remission', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    transport = fields.Char('Transport', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    photo = fields.Binary('Factura formato XML', help="Cargar el archivo xml para firma y autorizacion", states=_STATES)
    state = fields.Selection([
            ('pending', 'Pending'),
            ('review', 'In Review'),
            ('ready','Ready'),
            ('without','Without Solution'),
            ('warranty','Warranty not cover'),
            ('delivered', 'Delivered')
            ], 'State', readonly=True)
    lines = fields.One2Many('service.service.line', 'service', 'Lines', states=_STATES)

    accessories= fields.Text('Accessories', states=_STATES)
    observations = fields.Text('Observations', states=_STATES)
    history_lines = fields.One2Many('service.service.history_lines', 'service', 'Lines')


    @classmethod
    def __setup__(cls):
        super(Service, cls).__setup__()

        cls._error_messages.update({
                'modify_invoice': ('You can not modify service "%s" because '
                    'it is delivered.'),
                'delete_cancel': ('You can not modify service "%s" because '
                    'it is delivered.'),
                })

        cls._transitions |= set((
                ('pending', 'review'),
                ('review', 'ready'),
                ('review', 'without'),
                ('review', 'warranty'),
                ('ready', 'delivered'),
                ('without', 'delivered'),
                ('warranty', 'delivered'),
                ))

        cls._buttons.update({
                'review': {
                    'invisible': Eval('state') != ('pending')
                },
                'ready': {
                    'invisible': Eval('state').in_(['ready', 'without', 'delivered'])
                },
                'without': {
                    'invisible': Eval('state').in_(['ready', 'without', 'delivered'])
                },
                'warranty': {
                    'invisible': (~Eval('garanty', True))
                },
                'delivered': {
                    'invisible': Eval('state').in_(['pending', 'delivered'])
                },
            })

    @staticmethod
    def default_entry_date():
        Date = Pool().get('ir.date')
        return Date.today()

    @staticmethod
    def default_state():
        return 'pending'

    @staticmethod
    def default_type():
        return 'service'

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @classmethod
    def get_amount(cls, services, names):
        amount = Decimal(0.0)
        total = dict((i.id, _ZERO) for i in services)
        for service in services:
            for line in service.lines:
                amount += line.reference_amount
            total[service.id] = amount

        result = {
            'total': total,
            }
        for key in result.keys():
            if key not in names:
                del result[key]
        return result

    def set_number(self):
        pool = Pool()
        Period = pool.get('account.period')
        Sequence = pool.get('ir.sequence.strict')
        Date = pool.get('ir.date')

        if self.number_service:
            return

        test_state = True

        accounting_date = self.entry_date
        period_id = Period.find(self.company.id,
            date=accounting_date, test_state=test_state)
        period = Period(period_id)
        sequence = period.get_service_sequence(self.type)
        if not sequence:
            self.raise_user_error('no_withholding_sequence', {
                    'withholding': self.rec_name,
                    'period': period.rec_name,
                    })
        with Transaction().set_context(
                date=self.entry_date or Date.today()):
            number = Sequence.get_id(sequence.id)
            vals = {'number_service': number}
            if (not self.entry_date
                    and self.type in ('service')):
                vals['entry_date'] = Transaction().context['date']
        self.write([self], vals)

    @classmethod
    def check_modify(cls, services):
        for service in services:
            if (service.state in ('delivered')):
                cls.raise_user_error('modify_invoice', (service.number_service,))

    @classmethod
    def delete(cls, services):
        cls.check_modify(services)
        for service in services:
            if (service.state in ('review', 'ready', 'without', 'warranty', 'delivered')):
                cls.raise_user_error('delete_cancel', (service.number_service,))
        super(Service, cls).delete(services)

    @classmethod
    @ModelView.button
    @Workflow.transition('review')
    def review(cls, services):
        for service in services:
            service.set_number()

        cls.write([i for i in services if i.state != 'review'], {
                'state': 'review',
                })

    @classmethod
    @ModelView.button
    @Workflow.transition('ready')
    def ready(cls, services):
        cls.write([i for i in services if i.state != 'ready'], {
                'state': 'ready',
                })

    @classmethod
    @ModelView.button
    @Workflow.transition('without')
    def without(cls, services):
        cls.write([i for i in services if i.state != 'without'], {
                'state': 'without',
                })

    @classmethod
    @ModelView.button
    @Workflow.transition('warranty')
    def warranty(cls, services):
        cls.write([i for i in services if i.state != 'warranty'], {
                'state': 'warranty',
                })

    @classmethod
    @ModelView.button
    @Workflow.transition('delivered')
    def delivered(cls, services):
        cls.write([i for i in services if i.state != 'delivered'], {
                'state': 'delivered',
                })

class ServiceLine(ModelSQL, ModelView):
    'Service Line'
    __name__ = 'service.service.line'

    service = fields.Many2One('service.service', 'Service', ondelete='CASCADE',
        select=True)

    product = fields.Many2One('product.product', 'Type Work')
    periferic = fields.Many2One('service.periferic', 'Periferic')
    trademark = fields.Many2One('product.brand', 'Trademark')
    model = fields.Char('Model')
    series = fields.Char('Series')
    failure = fields.Text('Failure')
    reference_amount = fields.Numeric('Reference Amount')
    technical = fields.Many2One('company.employee', 'Technical')
    #type_work = fields.Many2One('service.type_work', 'Type Work')

    @classmethod
    def __setup__(cls):
        super(ServiceLine, cls).__setup__()
        cls._error_messages.update({
                'modify': ('You can not modify line "%(line)s" from service '
                    '"%(invoice)s" that is delivered.'),
                'create': ('You can not add a line to service "%(invoice)s" '
                    'that is delivered.'),
                })

    @staticmethod
    def default_series():
        return "S/S"

    @fields.depends('product', '_parent_service.party',
        '_parent_service.currency',
        'party', 'currency', 'service', 'reference_amount')
    def on_change_product(self):
        pool = Pool()
        Product = pool.get('product.product')
        Company = pool.get('company.company')
        Currency = pool.get('currency.currency')
        Date = pool.get('ir.date')

        if not self.product:
            return {}
        res = {}

        context = {}
        party = None

        currency_date = Date.today()
        if Transaction().context.get('company'):
            company = Company(Transaction().context['company'])
        currency = company.currency
        if company and currency:
            with Transaction().set_context(date=currency_date):
                res['reference_amount'] = Currency.compute(
                    company.currency, self.product.cost_price,
                    currency, round=False)

        return res

    @classmethod
    def check_modify(cls, lines):
        for line in lines:
            if (line.service
                    and line.service.state in ('review', 'ready', 'without', 'warranty', 'delivered')):
                cls.raise_user_error('modify', {
                        'line': line.rec_name,
                        'invoice': line.service.number_service
                        })

    @classmethod
    def delete(cls, lines):
        cls.check_modify(lines)
        super(ServiceLine, cls).delete(lines)

    @classmethod
    def write(cls, *args):
        lines = sum(args[0::2], [])
        cls.check_modify(lines)
        super(ServiceLine, cls).write(*args)

    @classmethod
    def create(cls, vlist):
        Service = Pool().get('service.service')
        service_ids = []
        for vals in vlist:
            if vals.get('service'):
                service_ids.append(vals.get('service'))
        for service in Service.browse(service_ids):
            if service.state in ('ready', 'without', 'warranty', 'delivered'):
                cls.raise_user_error('create', (service.number_service,))
        return super(ServiceLine, cls).create(vlist)

class HistoryLine(ModelSQL, ModelView):
    'History Line'
    __name__ = 'service.service.history_lines'

    service = fields.Many2One('service.service', 'Service', ondelete='CASCADE',
        select=True)
    description = fields.Text('Description', states={
        'readonly': Eval('description') != '',
    })
    date = fields.DateTime('Hora')

    @classmethod
    def __setup__(cls):
        super(HistoryLine, cls).__setup__()
        cls._error_messages.update({
                'modify': ('You can not modify line "%(line)s" from history '
                    '"%(invoice)s"'),
                'create': ('You can not add a line to history "%(invoice)s" '
                    'that is delivered.'),
                })
    """
    @staticmethod
    def default_date():
        Date = Pool().get('ir.datetime')
        return Date.today()
    """
    @staticmethod
    def default_description():
        return ''

    @classmethod
    def check_modify(cls, lines):
        for line in lines:
            if (line.service
                    and line.service.state in ('delivered')):
                cls.raise_user_error('modify', {
                        'line': line.rec_name,
                        'invoice': line.service.number_service
                        })

    @classmethod
    def delete(cls, lines):
        cls.check_modify(lines)
        for line in lines:
            if (line.service and line.service.state in ('review', 'ready', 'without', 'warranty', 'delivered')):
                cls.raise_user_error('modify', {
                        'line': line.rec_name,
                        'invoice': line.service.number_service
                        })
        super(HistoryLine, cls).delete(lines)

    """
    @classmethod
    def write(cls, *args):
        lines = sum(args[0::2], [])
        cls.check_modify(lines)
        super(HistoryLine, cls).write(*args)

    @classmethod
    def create(cls, vlist):
        Service = Pool().get('service.service')
        service_ids = []
        for vals in vlist:
            if vals.get('service'):
                service_ids.append(vals.get('service'))
        for service in Service.browse(service_ids):
            if service.state in ('delivered'):
                cls.raise_user_error('create', (service.number_service,))
        return super(HistoryLine, cls).create(vlist)
    """
class ServiceReport(Report):
    __name__ = 'service.service'

    @classmethod
    def __setup__(cls):
        super(ServiceReport, cls).__setup__()
        cls.__rpc__['execute'] = RPC(False)

    @classmethod
    def execute(cls, ids, data):
        Service = Pool().get('service.service')

        res = super(ServiceReport, cls).execute(ids, data)
        if len(ids) > 1:
            res = (res[0], res[1], True, res[3])
        else:
            service = Service(ids[0])
            if service.number_service:
                res = (res[0], res[1], res[2], res[3] + ' - ' + service.number_service)
        return res

    @classmethod
    def _get_records(cls, ids, model, data):
        with Transaction().set_context(language=False):
            return super(ServiceReport, cls)._get_records(ids[:1], model, data)

    @classmethod
    def parse(cls, report, records, data, localcontext):
        pool = Pool()
        User = pool.get('res.user')
        Service = pool.get('service.service')

        service = records[0]

        user = User(Transaction().user)
        localcontext['company'] = user.company
        return super(ServiceReport, cls).parse(report, records, data,
                localcontext=localcontext)
