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
        'Service Center Sequence',
        domain=[
            ['OR',
                ('company', '=', Eval('company')),
                ('company', '=', None),
                ],
            ],
        context={
            'company': Eval('company'),
            },
        depends=['company'])

    @classmethod
    def validate(cls, years):
        super(FiscalYear, cls).validate(years)
        for year in years:
            year.check_service_sequences()

    def check_service_sequences(self):
        for sequence in ('service_sequence', 'service_sequence'):
            fiscalyears = self.search([
                    (sequence, '=', getattr(self, sequence).id),
                    ('id', '!=', self.id),
                    ])
            if fiscalyears:
                self.raise_user_error('different_invoice_sequence', {
                        'first': self.rec_name,
                        'second': fiscalyears[0].rec_name,
                        })

    @classmethod
    def write(cls, *args):
        Service = Pool().get('service.service')

        actions = iter(args)
        for fiscalyears, values in zip(actions, actions):
            for sequence in ('service_sequence', 'service_sequence'):
                    if not values.get(sequence):
                        continue
                    for fiscalyear in fiscalyears:
                        if (getattr(fiscalyear, sequence)
                                and (getattr(fiscalyear, sequence).id !=
                                    values[sequence])):
                            if Service.search([
                                        ('entry_date', '>=',
                                            fiscalyear.start_date),
                                        ('entry_date', '<=',
                                            fiscalyear.end_date),
                                        ('number_service', '!=', None),
                                        ('type', '=', sequence[:-9]),
                                        ]):
                                cls.raise_user_error('change_invoice_sequence',
                                    (fiscalyear.rec_name,))
        super(FiscalYear, cls).write(*args)

class Period:
    __name__ = 'account.period'

    service_sequence = fields.Many2One('ir.sequence.strict',
        'Service Center Sequence',
        states={
            'invisible': Eval('type') != 'standard',
            },
        depends=['type'])

    @classmethod
    def validate(cls, periods):
        super(Period, cls).validate(periods)
        for period in periods:
            period.check_service_sequences()

    def check_service_sequences(self):
        for sequence_name in ('service_sequence', 'service_sequence'):
            sequence = getattr(self, sequence_name)
            if not sequence:
                continue
            periods = self.search([
                    (sequence_name, '=', sequence.id),
                    ('fiscalyear', '!=', self.fiscalyear.id),
                    ])
            if periods:
                self.raise_user_error('different_invoice_sequence', {
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
                for sequence in ('service_sequence', 'service_sequence'):
                    if not vals.get(sequence):
                        vals[sequence] = getattr(fiscalyear, sequence).id
        return super(Period, cls).create(vlist)

    @classmethod
    def write(cls, *args):
        Service = Pool().get('service.service')

        actions = iter(args)
        for periods, values in zip(actions, actions):
            for sequence_name in ('service_sequence', 'service_sequence'):
                if not values.get(sequence_name):
                    continue
                for period in periods:
                    sequence = getattr(period, sequence_name)
                    if (sequence and sequence.id != values[sequence_name]):
                        if Service.search([
                                    ('entry_date', '>=', period.start_date),
                                    ('entry_date', '<=', period.end_date),
                                    ('number_service', '!=', None),
                                    ('type', '=', sequence_name[:-9]),
                                    ]):
                            cls.raise_user_error('change_invoice_sequence',
                                (period.rec_name,))
        super(Period, cls).write(*args)

    def get_service_sequence(self, invoice_type):
        sequence = getattr(self, invoice_type + '_sequence')
        if sequence:
            return sequence
        return getattr(self.fiscalyear, invoice_type + '_sequence')
