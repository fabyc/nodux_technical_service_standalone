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
from trytond import security
try:
    import bcrypt
except ImportError:
    bcrypt = None
import random
import hashlib
import string
#from datetime import timedelta

_ZERO = Decimal('0.0')

_TYPE = [
    ('service', 'Servicio'),
    ('home_service', 'Servicio a domicilio')
]

__all__ = ['Periferic', 'Service', 'ServiceLine', 'HistoryLine',
            'ServiceReport', 'DraftServiceStart', 'DraftService']

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
    party = fields.Many2One('party.party', 'Party', states=_STATES, required=True)
    number_service = fields.Char('No. Comprobante', readonly=True)
    type = fields.Selection(_TYPE, 'Type', select=True, states={
        'readonly': ((Eval('state') == 'delivered')
            | Eval('context', {}).get('type')),
        })

    total = fields.Function(fields.Numeric('Total', states={
        'invisible': Eval('type') == 'home_service',
    }), 'get_amount')

    entry_date = fields.Date('Entry Date', states=_STATES,
        domain=[('entry_date', '<', Eval('delivery_date', None))],
        depends=['delivery_date'])
    delivery_date = fields.Date('Estimated Delivery Date', states=_STATES,
        domain=[('delivery_date', '>', Eval('entry_date', None))],
        depends=['entry_date'])
    technical = fields.Many2One('company.employee', 'Technical', states=_STATES)
    garanty = fields.Boolean('Garanty', help="Income Garanty", states=_STATES)
    new = fields.Boolean('New', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    lined = fields.Boolean('Lined', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    beaten = fields.Boolean('Beaten', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    broken = fields.Boolean('Broken', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
    stained = fields.Boolean('Stained', states={
            'invisible': ~Eval('garanty', True),
            'readonly': Eval('state') == 'delivered',
    })
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
    photo = fields.Binary('Foto', states=_STATES)
    state = fields.Selection([
            ('pending', 'Pending'),
            ('review', 'In Review'),
            ('ready','Ready'),
            ('without','Without Solution'),
            ('warranty','Warranty not cover'),
            ('delivered', 'Delivered')
            ], 'State', readonly=True)
    lines = fields.One2Many('service.service.line', 'service', 'Lines', states=_STATES)

    accessories= fields.Text('Accessories', states={
        'readonly': Eval('accessories') != '',
    })
    observations = fields.Text('Observations', states=_STATES)
    history_lines = fields.One2Many('service.service.history_lines', 'service', 'Lines')
    total_home_service = fields.Numeric('Total', states={
        'invisible': Eval('type') == 'service',
    })
    state_date = fields.Function(fields.Char('State Date'), 'get_state_date')
    detail = fields.Text('Repair Detail',  states={
        'invisible': Eval('state') != 'delivered',
        'readonly': Eval('detail') != '',
    })

    @classmethod
    def __setup__(cls):
        super(Service, cls).__setup__()

        cls.__rpc__['getTechnicalService'] = RPC(check_access=False, readonly=False)

        cls._error_messages.update({
                'modify_invoice': ('You can not modify service "%s".'),
                'delete_cancel': ('You can not delete service "%s".'),
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
                    'invisible': Eval('state').in_(['pending','ready', 'without', 'delivered'])
                },
                'without': {
                    'invisible': Eval('state').in_(['pending','ready', 'without', 'delivered'])
                },
                'warranty': {
                    'invisible': ~Eval('garanty', True) | (Eval('state').in_(['pending','ready', 'without', 'delivered']))
                },
                'delivered': {
                    'invisible': Eval('state').in_(['review','pending', 'delivered'])
                },
            })

    @fields.depends('invoice_date', 'garanty')
    def on_change_invoice_date(self):
        res = {}
        Date = Pool().get('ir.date')
        if self.garanty != None:
            year = Date.today()- datetime.timedelta(days=365)
            if self.invoice_date < year:
                res['invoice_date'] =  self.invoice_date
                self.raise_user_error(u'Está seguro de la fecha de ingreso: "%s"'
                    u'tiene mas de un año de garantia', (self.invoice_date))
        else:
            res['invoice_date'] =  self.invoice_date

        return res

    @classmethod
    def get_state_date(cls, services, names):
        pool = Pool()
        Date = pool.get('ir.date')
        date_now = Date.today()
        result = {n: {s.id: '' for s in services} for n in names}
        for name in names:
            for service in services:
                if (service.delivery_date < date_now) and (service.state != 'delivered'):
                    result[name][service.id] = 'vencida'
                elif (service.delivery_date == date_now) and (service.state != 'delivered'):
                    result[name][service.id] = 'vence_hoy'
                else:
                    result[name][service.id] = ''
        return result

    @staticmethod
    def default_entry_date():
        Date = Pool().get('ir.date')
        return Date.today()

    @staticmethod
    def default_accessories():
        return ''

    @staticmethod
    def default_detail():
        return ''

    @staticmethod
    def default_delivery_date():
        Date = Pool().get('ir.date')
        return Date.today()+ datetime.timedelta(days=1)

    @staticmethod
    def default_state():
        return 'pending'

    @staticmethod
    def default_type():
        return Transaction().context.get('type', 'service')

    @staticmethod
    def default_company():
        return Transaction().context.get('company')

    @classmethod
    def get_amount(cls, services, names):
        amount = Decimal(0.0)
        total = dict((i.id, _ZERO) for i in services)
        for service in services:
            for line in service.lines:
                if line.reference_amount:
                    amount += line.reference_amount
            total[service.id] = amount

        result = {
            'total': total,
            }
        for key in result.keys():
            if key not in names:
                del result[key]
        return result

    @fields.depends('total', 'total_home_service')
    def on_change_total_home_service(self):
        res = {}

        if self.total_home_service:
            res['total'] =  self.total_home_service
        else:
            res['total'] = Decimal(0.0)

        return res

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

    @classmethod
    def getTechnicalService(cls, identificacion):
        print "Establece la conexion ", identificacion
        pool = Pool()
        Service = pool.get('service.service')
        Party = pool.get('party.party')
        parties = Party.search([('vat_number', '=', identificacion)])
        for p in parties:
            party = p
        services = Service.search([('party', '=', party)])
        print "Services", services
        all_services = []
        if services:
            for service in services:
                lines_services = {}
                for line in service.lines:
                    lines_services[0] = str(service.entry_date)
                    lines_services[1]= str(service.delivery_date)
                    lines_services[2] = service.number_service
                    lines_services[3] = line.periferic.name
                    lines_services[4] = line.trademark.name
                    lines_services[5] = line.model
                    lines_services[6] = line.failure
                    lines_services[7] = str(line.reference_amount)
                    lines_services[8] = line.technical.party.name
                    lines_services[9] = service.state
                    lines_services[10] = service.accessories
                    lines_services[11] = service.detail
                    all_services.append(lines_services)
            print "Servicios ", all_services
            return all_services
        else:
            return []

class ServiceLine(ModelSQL, ModelView):
    'Service Line'
    __name__ = 'service.service.line'

    service = fields.Many2One('service.service', 'Service', ondelete='CASCADE',
        select=True)

    product = fields.Many2One('product.product', 'Type Work', required = True)
    periferic = fields.Many2One('service.periferic', 'Periferic', required = True)
    trademark = fields.Many2One('product.brand', 'Trademark', required = True)
    model = fields.Char('Model', required = True)
    series = fields.Char('Series')
    failure = fields.Text('Failure', required = True)
    reference_amount = fields.Numeric('Reference Amount')
    technical = fields.Many2One('company.employee', 'Technical', required = True)
    #type_work = fields.Many2One('service.type_work', 'Type Work')

    @classmethod
    def __setup__(cls):
        super(ServiceLine, cls).__setup__()
        cls._error_messages.update({
                'modify': ('You can not modify line "%(line)s" from service '
                    '"%(invoice)s".'),
                'create': ('You can not add a line to service "%(invoice)s."'),
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

    user = fields.Char('Usuario', required = True)

    password = fields.Char('Password', required = True, size=20, states={
        'readonly': Eval('user') != '',
    })

    @classmethod
    def __setup__(cls):
        super(HistoryLine, cls).__setup__()
        cls._error_messages.update({
                'modify': ('You can not modify line "%(line)s" from history '
                    '"%(invoice)s"'),
                'create': ('You can not add a line to history "%(invoice)s" '),
                })
    @staticmethod
    def default_date():
        return datetime.datetime.now()

    def hash_password(self, password):
        if not password:
            return ''
        return getattr(self, 'hash_' + self.hash_method())(password)

    @staticmethod
    def hash_method():
        return 'bcrypt' if bcrypt else 'sha1'

    @classmethod
    def hash_sha1(cls, password):
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        salt = ''.join(random.sample(string.ascii_letters + string.digits, 8))
        hash_ = hashlib.sha1(password + salt).hexdigest()
        return '$'.join(['sha1', hash_, salt])

    def check_password(self, password, hash_):
        if not hash_:
            return False
        hash_method = hash_.split('$', 1)[0]
        return getattr(self, 'check_' + hash_method)(password, hash_)

    @classmethod
    def check_sha1(cls, password, hash_):
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        if isinstance(hash_, unicode):
            hash_ = hash_.encode('utf-8')
        hash_method, hash_, salt = hash_.split('$', 2)
        salt = salt or ''
        assert hash_method == 'sha1'
        return hash_ == hashlib.sha1(password + salt).hexdigest()

    @classmethod
    def hash_bcrypt(cls, password):
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        hash_ = bcrypt.hashpw(password, bcrypt.gensalt())
        return '$'.join(['bcrypt', hash_])

    @classmethod
    def check_bcrypt(cls, password, hash_):
        if isinstance(password, unicode):
            password = password.encode('utf-8')
        if isinstance(hash_, unicode):
            hash_ = hash_.encode('utf-8')
        hash_method, hash_ = hash_.split('$', 1)
        assert hash_method == 'bcrypt'
        return hash_ == bcrypt.hashpw(password, hash_)

    @fields.depends('description', 'password')
    def on_change_password(self):
        res = {}
        User = Pool().get('res.user')
        user = None
        value = False
        if self.description:
            if self.password:
                users = User.search([('password_hash', '!=', None)])
                if users:
                    for u in users:
                        value = self.check_password(self.password, u.password_hash)
                        if value == True:
                            res['user'] = u.name
                            break
                if value == False:
                    self.raise_user_error(u'Contraseña no válida')
        else:
            res['user'] = user
        return res

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

class DraftServiceStart(ModelView):
    'Draft Service Start'
    __name__ = 'service.draft_service.start'


class DraftService(Wizard):
    'Draft Service'
    __name__ = 'service.draft_service'
    start = StateView('service.draft_service.start',
        'nodux_technical_service.draft_service_start_view_form', [
            Button('Exit', 'end', 'tryton-cancel'),
            Button('Reverse', 'draft_', 'tryton-ok', default=True),
            ])
    draft_ = StateAction('nodux_technical_service.act_service_form')

    def do_draft_(self, action):
        pool = Pool()
        Service = pool.get('service.service')
        services = Service.browse(Transaction().context['active_ids'])

        origin = str(services)
        def in_group():
            pool = Pool()
            ModelData = pool.get('ir.model.data')
            User = pool.get('res.user')
            Group = pool.get('res.group')
            group = Group(ModelData.get_id('nodux_technical_service',
                        'group_service_reverse'))
            transaction = Transaction()
            user_id = transaction.user
            if user_id == 0:
                user_id = transaction.context.get('user', user_id)
            if user_id == 0:
                return True
            user = User(user_id)
            return origin and group in user.groups
        if not in_group():
            self.raise_user_error("No esta autorizado a reversar un Servicio")

        for service in services:
            service.state = 'review'
            service.save()
