#This file is part of Tryton.  The COPYRIGHT file at the top level of
#this repository contains the full copyright notices and license terms.
from trytond.model import ModelSQL, ModelView, MatchMixin, fields
from trytond.pyson import Eval
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction

__all__ = ['FiscalYear', 'Period']
__metaclass__ = PoolMeta

class FiscalYear:
    __name__ = 'account.fiscalyear'

    service_sequence = fields.Many2One('ir.sequence.strict',
        'Service Center Sequence', required= True,
        domain=[
            ('code', '=', 'service.service'),
            ['OR',
                ('company', '=', Eval('company')),
                ('company', '=', None),
                ],
            ],
        context={
            'code': 'service.service',
            'company': Eval('company'),
            },
        depends=['company'])

    @classmethod
    def __setup__(cls):
        super(FiscalYear, cls).__setup__()
        cls._error_messages.update({
                'change_invoice_sequence': 'You can not change '
                    'invoice sequence in fiscal year "%s" because there are '
                    'already posted invoices in this fiscal year.',
                'different_service_sequence': 'Fiscal year "%(first)s" and '
                    '"%(second)s" have the same invoice sequence.',
                })

    @classmethod
    def validate(cls, years):
        super(FiscalYear, cls).validate(years)
        for year in years:
            year.check_service_sequences()

    def check_service_sequences(self):
        fiscalyears = self.search([
                ('service_sequence', '=', getattr(self, 'service_sequence').id),
                ('id', '!=', self.id),
                ])
        if fiscalyears:
            self.raise_user_error('different_service_sequence', {
                    'first': self.rec_name,
                    'second': fiscalyears[0].rec_name,
                    })

    @classmethod
    def write(cls, *args):
        Service = Pool().get('service.service')
        actions = iter(args)
        for fiscalyears, values in zip(actions, actions):
            if not values.get('service_sequence'):
                continue
            for fiscalyear in fiscalyears:
                if (getattr(fiscalyear, 'service_sequence')
                        and (getattr(fiscalyear, 'service_sequence').id !=
                            values['service_sequence'])):
                    if Service.search([
                                ('entry_date', '>=',
                                    fiscalyear.start_date),
                                ('entry_date', '<=',
                                    fiscalyear.end_date),
                                ('number_service', '!=', None),
                                ('type', '=', 'service_sequence'[:-9]),
                                ]):
                        cls.raise_user_error('change_service_sequence',
                            (fiscalyear.rec_name,))
        super(FiscalYear, cls).write(*args)

class Period:
    __name__ = 'account.period'

    service_sequence = fields.Many2One('ir.sequence.strict',
        'Service Center Sequence',
        domain=[('code', '=', 'service.service')],
        context={'code': 'service.service'},
        states={
            'invisible': Eval('type') != 'standard',
            },
        depends=['type'])

    @classmethod
    def __setup__(cls):
        super(Period, cls).__setup__()
        cls._error_messages.update({
                'change_service_sequence': 'You can not change the service '
                    'sequence in period "%s" because there is already an '
                    'service posted in this period',
                'different_service_sequence': 'Period "%(first)s" and '
                    '"%(second)s" have the same service sequence.',
                'different_period_fiscalyear_company': 'Period "%(period)s" '
                    'must have the same company as its fiscal year '
                    '(%(fiscalyear)s).'
                })

    @classmethod
    def validate(cls, periods):
        super(Period, cls).validate(periods)
        for period in periods:
            period.check_service_sequences()

    def check_service_sequences(self):
        sequence = getattr(self, 'service_sequence')

        periods = self.search([
                ('service_sequence', '=', sequence.id),
                ('fiscalyear', '!=', self.fiscalyear.id),
                ])
        if periods:
            self.raise_user_error('different_service_sequence', {
                    'first': self.rec_name,
                    'second': periods[0].rec_name,
                    })
        if (sequence.company
                and sequence.company != self.fiscalyear.company):
            self.raise_user_error('different_period_fiscalyear_company', {
                    'period': self.rec_name,
                    'fiscalyear': self.fiscalyear.rec_name,
                    })

    @classmethod
    def create(cls, vlist):
        FiscalYear = Pool().get('account.fiscalyear')
        vlist = [v.copy() for v in vlist]
        for vals in vlist:
            if vals.get('fiscalyear'):
                fiscalyear = FiscalYear(vals['fiscalyear'])
                if not vals.get('service_sequence'):
                    vals['service_sequence'] = getattr(fiscalyear, 'service_sequence').id
        return super(Period, cls).create(vlist)

    @classmethod
    def write(cls, *args):
        Service = Pool().get('service.service')

        actions = iter(args)
        for periods, values in zip(actions, actions):
            if not values.get('service_sequence'):
                continue
            for period in periods:
                sequence = getattr(period, 'service_sequence')
                if (sequence and sequence.id != values['service_sequence']):
                    if Service.search([
                                ('entry_date', '>=', period.start_date),
                                ('entry_date', '<=', period.end_date),
                                ('number_service', '!=', None),
                                ('type', '=', sequence_name[:-9]),
                                ]):
                        cls.raise_user_error('change_service_sequence',
                            (period.rec_name,))
        super(Period, cls).write(*args)

    def get_service_sequence(self, invoice_type):
        sequence = getattr(self, invoice_type + '_sequence')
        if sequence:
            return sequence
        return getattr(self.fiscalyear, invoice_type + '_sequence')
