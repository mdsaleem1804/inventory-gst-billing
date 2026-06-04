from datetime import datetime

from flask import render_template, request, redirect, url_for, flash, send_file, Response
from flask_login import login_required, current_user
from sqlalchemy import func
import io
import pandas as pd

from models import db, Expense, ExpenseCategory, BankAccount, Payment, ActivityLog, is_finance_feature_enabled
from .routes import finance_bp


def _export_amount(value):
    return f"{float(value or 0):.2f}"


def _is_finance_editor():
    return current_user.role in ('admin', 'approver')


def _require_finance_feature():
    if not is_finance_feature_enabled():
        flash('Finance module is disabled for this customer.', 'warning')
        return False
    return True


def _normalize_payment_mode(mode):
    if mode is None:
        return None
    value = str(mode).strip().lower().replace('-', ' ').replace('_', ' ')
    if not value:
        return None
    if value in {'cash'}:
        return 'cash'
    if value in {'upi'}:
        return 'upi'
    if value in {'card', 'credit card', 'debit card'}:
        return 'card'
    if value in {'bank transfer', 'banktransfer', 'neft', 'rtgs', 'imps'}:
        return 'bank_transfer'
    if value in {'cheque', 'check'}:
        return 'cheque'
    return value.replace(' ', '_')


def _is_bank_mode(mode):
    return _normalize_payment_mode(mode) in {'upi', 'card', 'bank_transfer', 'cheque'}


def _log_finance(action, details):
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action=action,
            details=details,
        )
    )
    db.session.commit()


@finance_bp.route('/expenses', methods=['GET', 'POST'])
@login_required
def expenses():
    if not _require_finance_feature():
        return redirect(url_for('dashboard.dashboard'))
    if request.method == 'POST':
        if not _is_finance_editor():
            flash('Only admin or approver can add/delete expenses.', 'danger')
            return redirect(url_for('finance.expenses'))

        delete_id = request.form.get('delete_id', type=int)
        if delete_id:
            expense = Expense.query.get(delete_id)
            if expense:
                db.session.delete(expense)
                db.session.commit()
                _log_finance('Expense Deleted', f'Expense id={delete_id} deleted')
                flash('Expense deleted.', 'success')
            return redirect(url_for('finance.expenses'))

        expense_date_str = (request.form.get('expense_date') or '').strip()
        category_id = request.form.get('category_id', type=int)
        new_category = (request.form.get('new_category') or '').strip()
        amount = request.form.get('amount', type=float)
        payment_mode = _normalize_payment_mode(request.form.get('payment_mode') or 'cash') or 'cash'
        bank_account_id = request.form.get('bank_account_id', type=int)
        reference_no = (request.form.get('reference_no') or '').strip()
        description = (request.form.get('description') or '').strip()

        if not amount or amount <= 0:
            flash('Enter a valid expense amount.', 'danger')
            return redirect(url_for('finance.expenses'))
        if _is_bank_mode(payment_mode) and not bank_account_id:
            flash('Select a bank account for non-cash expense.', 'danger')
            return redirect(url_for('finance.expenses'))

        if new_category:
            existing = ExpenseCategory.query.filter(func.lower(ExpenseCategory.name) == new_category.lower()).first()
            if existing:
                category = existing
            else:
                category = ExpenseCategory(name=new_category)
                db.session.add(category)
                db.session.flush()
        else:
            category = ExpenseCategory.query.get(category_id) if category_id else None

        if not category:
            flash('Select or create an expense category.', 'danger')
            return redirect(url_for('finance.expenses'))

        expense_date = datetime.now()
        if expense_date_str:
            try:
                expense_date = datetime.strptime(expense_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Expense date is invalid.', 'danger')
                return redirect(url_for('finance.expenses'))

        expense = Expense(
            expense_date=expense_date,
            category_id=category.id,
            amount=round(amount, 2),
            payment_mode=payment_mode,
            bank_account_id=bank_account_id if _is_bank_mode(payment_mode) else None,
            reference_no=reference_no or None,
            description=description or None,
            created_by_user_id=current_user.id,
        )
        db.session.add(expense)
        db.session.commit()

        _log_finance(
            'Expense Added',
            (
                f'category={category.name}; amount={round(amount, 2)}; mode={payment_mode}; '
                f'bank_account_id={bank_account_id or "-"}; reference={reference_no or "-"}'
            ),
        )
        flash('Expense recorded.', 'success')
        return redirect(url_for('finance.expenses'))

    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    search = request.args.get('search', '').strip()
    export = request.args.get('export', '').strip().lower()

    query = Expense.query
    if from_date:
        query = query.filter(func.date(Expense.expense_date) >= from_date)
    if to_date:
        query = query.filter(func.date(Expense.expense_date) <= to_date)
    if search:
        query = query.join(ExpenseCategory).filter(
            ExpenseCategory.name.ilike(f'%{search}%') |
            Expense.description.ilike(f'%{search}%') |
            Expense.reference_no.ilike(f'%{search}%')
        )

    expenses_list = query.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()
    categories = ExpenseCategory.query.filter_by(is_active=True).order_by(ExpenseCategory.name.asc()).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).order_by(BankAccount.account_name.asc()).all()
    total_expense = round(sum(float(e.amount or 0) for e in expenses_list), 2)

    if export == 'csv':
        rows = [
            {
                'Date': e.expense_date.strftime('%Y-%m-%d') if e.expense_date else '',
                'Category': e.category.name if e.category else '',
                'Amount': _export_amount(e.amount),
                'Mode': e.payment_mode or '',
                'Bank Account': e.bank_account.account_name if e.bank_account else '',
                'Reference': e.reference_no or '',
                'Description': e.description or '',
            }
            for e in expenses_list
        ]
        df = pd.DataFrame(rows)
        csv_content = df.to_csv(index=False)
        _log_finance('Expense Report Exported CSV', f'rows={len(rows)} from={from_date or "-"} to={to_date or "-"} search={search or "-"}')
        return Response(csv_content, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=expenses_report.csv'})

    if export == 'excel':
        rows = [
            {
                'Date': e.expense_date.strftime('%Y-%m-%d') if e.expense_date else '',
                'Category': e.category.name if e.category else '',
                'Amount': _export_amount(e.amount),
                'Mode': e.payment_mode or '',
                'Bank Account': e.bank_account.account_name if e.bank_account else '',
                'Reference': e.reference_no or '',
                'Description': e.description or '',
            }
            for e in expenses_list
        ]
        df = pd.DataFrame(rows)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Expenses')
        buffer.seek(0)
        _log_finance('Expense Report Exported Excel', f'rows={len(rows)} from={from_date or "-"} to={to_date or "-"} search={search or "-"}')
        return send_file(buffer, as_attachment=True, download_name='expenses_report.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    return render_template(
        'finance/expenses.html',
        expenses=expenses_list,
        categories=categories,
        bank_accounts=bank_accounts,
        from_date=from_date,
        to_date=to_date,
        search=search,
        total_expense=total_expense,
        can_edit=_is_finance_editor(),
        today=datetime.now().strftime('%Y-%m-%d'),
    )


@finance_bp.route('/bank-book', methods=['GET'])
@login_required
def bank_book():
    if not _require_finance_feature():
        return redirect(url_for('dashboard.dashboard'))
    from_date = request.args.get('from_date', '')
    to_date = request.args.get('to_date', '')
    recently_mapped_payment_id = request.args.get('recently_mapped_payment_id', type=int)
    export = request.args.get('export', '').strip().lower()

    payment_query = Payment.query
    if from_date:
        payment_query = payment_query.filter(func.date(Payment.payment_date) >= from_date)
    if to_date:
        payment_query = payment_query.filter(func.date(Payment.payment_date) <= to_date)

    payment_rows = payment_query.order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    bank_collections = []
    unmapped_collections = []
    for pay in payment_rows:
        mode = _normalize_payment_mode(pay.payment_mode)
        if _is_bank_mode(mode):
            bank_collections.append(pay)
            if not pay.bank_account_id:
                unmapped_collections.append(pay)

    expense_query = Expense.query
    if from_date:
        expense_query = expense_query.filter(func.date(Expense.expense_date) >= from_date)
    if to_date:
        expense_query = expense_query.filter(func.date(Expense.expense_date) <= to_date)

    expense_rows = expense_query.order_by(Expense.expense_date.desc(), Expense.id.desc()).all()
    bank_expenses = []
    for exp in expense_rows:
        mode = _normalize_payment_mode(exp.payment_mode)
        if _is_bank_mode(mode):
            bank_expenses.append(exp)

    inflow_total = round(sum(float(p.amount or 0) for p in bank_collections), 2)
    outflow_total = round(sum(float(e.amount or 0) for e in bank_expenses), 2)
    net_bank_flow = round(inflow_total - outflow_total, 2)

    collection_items = [
        {
            'date': p.payment_date,
            'source': 'Invoice Payment',
            'reference': p.reference_no or '-',
            'mode': p.payment_mode or '-',
            'account': p.bank_account.account_name if p.bank_account else '-',
            'amount_in': round(float(p.amount or 0), 2),
            'amount_out': 0.0,
        }
        for p in bank_collections
    ]
    expense_items = [
        {
            'date': e.expense_date,
            'source': f'Expense: {e.category.name if e.category else "-"}',
            'reference': e.reference_no or '-',
            'mode': e.payment_mode or '-',
            'account': e.bank_account.account_name if e.bank_account else '-',
            'amount_in': 0.0,
            'amount_out': round(float(e.amount or 0), 2),
        }
        for e in bank_expenses
    ]

    ledger_rows = sorted(collection_items + expense_items, key=lambda r: r['date'] or datetime.min, reverse=True)

    if export == 'csv':
        rows = [
            {
                'Date': r['date'].strftime('%Y-%m-%d') if r['date'] else '',
                'Source': r['source'],
                'Mode': r['mode'],
                'Account': r['account'],
                'Reference': r['reference'],
                'In': _export_amount(r['amount_in']),
                'Out': _export_amount(r['amount_out']),
            }
            for r in ledger_rows
        ]
        df = pd.DataFrame(rows)
        csv_content = df.to_csv(index=False)
        _log_finance('Bank Book Exported CSV', f'rows={len(rows)} from={from_date or "-"} to={to_date or "-"}')
        return Response(csv_content, mimetype='text/csv', headers={'Content-Disposition': 'attachment; filename=bank_book.csv'})

    if export == 'excel':
        rows = [
            {
                'Date': r['date'].strftime('%Y-%m-%d') if r['date'] else '',
                'Source': r['source'],
                'Mode': r['mode'],
                'Account': r['account'],
                'Reference': r['reference'],
                'In': _export_amount(r['amount_in']),
                'Out': _export_amount(r['amount_out']),
            }
            for r in ledger_rows
        ]
        df = pd.DataFrame(rows)
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Bank Book')
        buffer.seek(0)
        _log_finance('Bank Book Exported Excel', f'rows={len(rows)} from={from_date or "-"} to={to_date or "-"}')
        return send_file(buffer, as_attachment=True, download_name='bank_book.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    unmapped_rows = [
        {
            'date': p.payment_date,
            'payment_id': p.id,
            'invoice_id': p.invoice_id,
            'invoice_number': p.invoice.invoice_number if p.invoice else '-',
            'customer_name': p.invoice.customer_name if p.invoice else '-',
            'mode': p.payment_mode or '-',
            'reference': p.reference_no or '-',
            'amount': round(float(p.amount or 0), 2),
        }
        for p in unmapped_collections
    ]
    unmapped_total = round(sum(float(r['amount']) for r in unmapped_rows), 2)

    recently_mapped_row = None
    if recently_mapped_payment_id:
        mapped_payment = Payment.query.get(recently_mapped_payment_id)
        if mapped_payment and _is_bank_mode(mapped_payment.payment_mode) and mapped_payment.bank_account_id:
            recently_mapped_row = {
                'date': mapped_payment.payment_date,
                'invoice_id': mapped_payment.invoice_id,
                'invoice_number': mapped_payment.invoice.invoice_number if mapped_payment.invoice else '-',
                'customer_name': mapped_payment.invoice.customer_name if mapped_payment.invoice else '-',
                'mode': mapped_payment.payment_mode or '-',
                'reference': mapped_payment.reference_no or '-',
                'account': mapped_payment.bank_account.account_name if mapped_payment.bank_account else '-',
                'amount': round(float(mapped_payment.amount or 0), 2),
            }

    return render_template(
        'finance/bank_book.html',
        from_date=from_date,
        to_date=to_date,
        inflow_total=inflow_total,
        outflow_total=outflow_total,
        net_bank_flow=net_bank_flow,
        ledger_rows=ledger_rows,
        unmapped_rows=unmapped_rows,
        unmapped_count=len(unmapped_rows),
        unmapped_total=unmapped_total,
        recently_mapped_row=recently_mapped_row,
        bank_modes=', '.join(['UPI', 'Card', 'Bank Transfer', 'Cheque']),
    )


@finance_bp.route('/bank-accounts', methods=['GET', 'POST'])
@login_required
def bank_accounts():
    if not _require_finance_feature():
        return redirect(url_for('dashboard.dashboard'))
    if request.method == 'POST':
        if not _is_finance_editor():
            flash('Only admin or approver can manage bank accounts.', 'danger')
            return redirect(url_for('finance.bank_accounts'))

        account_name = (request.form.get('account_name') or '').strip()
        account_type = (request.form.get('account_type') or 'current').strip().lower()
        opening_balance = request.form.get('opening_balance', type=float) or 0.0

        if not account_name:
            flash('Account name is required.', 'danger')
            return redirect(url_for('finance.bank_accounts'))

        exists = BankAccount.query.filter(func.lower(BankAccount.account_name) == account_name.lower()).first()
        if exists:
            flash('Bank account already exists.', 'warning')
            return redirect(url_for('finance.bank_accounts'))

        account = BankAccount(
            account_name=account_name,
            account_type=account_type,
            opening_balance=round(opening_balance, 2),
            is_active=True,
        )
        db.session.add(account)
        db.session.commit()
        _log_finance('Bank Account Added', f'name={account_name}; type={account_type}; opening={round(opening_balance, 2)}')
        flash('Bank account added.', 'success')
        return redirect(url_for('finance.bank_accounts'))

    accounts = BankAccount.query.order_by(BankAccount.account_name.asc()).all()
    return render_template('finance/bank_accounts.html', accounts=accounts, can_edit=_is_finance_editor())
