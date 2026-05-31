
import pandas as pd
from flask import send_file, render_template, redirect, url_for, flash, request
import io
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from flask_login import login_required, current_user
from .routes import invoices_bp
from models import db, Invoice, InvoiceItem, Product, ActivityLog, Payment, BankAccount
from datetime import datetime
from sqlalchemy import func


def _export_amount(value):
    return f"{float(value or 0):.2f}"


def _can_manage_invoices():
    return current_user.role in ('admin', 'approver')


def _can_manage_payments():
    return current_user.role in ('admin', 'approver')


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


def _is_non_cash_mode(mode):
    return _normalize_payment_mode(mode) in {'upi', 'card', 'bank_transfer', 'cheque'}


def _log_invoice_activity(action, details):
    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action=action,
            details=details,
        )
    )
    db.session.commit()


def _recalculate_invoice_payment(invoice):
    total = round(float(invoice.total or 0), 2)
    paid = round(float(invoice.paid_amount or 0), 2)
    if paid < 0:
        paid = 0
    balance = round(total - paid, 2)

    invoice.paid_amount = paid
    invoice.balance_amount = balance if balance > 0 else 0
    if paid <= 0:
        invoice.payment_status = 'unpaid'
    elif paid >= total:
        invoice.payment_status = 'paid'
    else:
        invoice.payment_status = 'partial'


def _sync_invoice_payment_from_transactions(invoice):
    paid_total = (
        db.session.query(func.coalesce(func.sum(Payment.amount), 0.0))
        .filter(Payment.invoice_id == invoice.id)
        .scalar()
        or 0.0
    )
    invoice.paid_amount = round(float(paid_total), 2)

    latest_payment = (
        Payment.query.filter_by(invoice_id=invoice.id)
        .order_by(Payment.payment_date.desc(), Payment.id.desc())
        .first()
    )
    if latest_payment:
        invoice.payment_date = latest_payment.payment_date
        invoice.payment_mode = latest_payment.payment_mode
        invoice.reference_no = latest_payment.reference_no
    else:
        invoice.payment_date = None
        invoice.payment_mode = None
        invoice.reference_no = None

    _recalculate_invoice_payment(invoice)


def _invoice_financial_snapshot(invoice):
    return (
        f"status={invoice.payment_status or '-'}"
        f", paid={round(float(invoice.paid_amount or 0), 2)}"
        f", balance={round(float(invoice.balance_amount if invoice.balance_amount is not None else invoice.total or 0), 2)}"
        f", total={round(float(invoice.total or 0), 2)}"
    )


def _payment_snapshot(payment):
    payment_date = payment.payment_date.strftime('%Y-%m-%d') if payment.payment_date else '-'
    return (
        f"id={payment.id}"
        f", amount={round(float(payment.amount or 0), 2)}"
        f", date={payment_date}"
        f", mode={payment.payment_mode or '-'}"
        f", bank_account_id={payment.bank_account_id if payment.bank_account_id else '-'}"
        f", ref={payment.reference_no or '-'}"
        f", notes={payment.notes or '-'}"
    )


def _can_receive_payment(invoice):
    return round(float(invoice.balance_amount or 0), 2) > 0

@invoices_bp.route('/export/excel')
@login_required
def export_invoices_excel():
    invoices = Invoice.query.order_by(Invoice.date.desc()).all()
    data = []
    for inv in invoices:
        data.append({
            'Invoice #': inv.invoice_number,
            'Date': inv.date.strftime('%Y-%m-%d'),
            'Customer': inv.customer_name,
            'GSTIN': inv.customer_gstin,
            'Total': _export_amount(inv.total),
            'CGST': _export_amount(inv.cgst),
            'SGST': _export_amount(inv.sgst)
        })
    df = pd.DataFrame(data)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Invoices')
    buffer.seek(0)
    _log_invoice_activity('Invoice Exported Excel', f'Exported {len(data)} invoices to Excel')
    return send_file(buffer, as_attachment=True, download_name='invoices.xlsx', mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@invoices_bp.route('/<int:invoice_id>/pdf')
@login_required
def download_invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    items = invoice.items
    buffer = io.BytesIO()
    p = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    y = height - 50
    p.setFont('Helvetica-Bold', 16)
    p.drawString(200, y, 'TAX INVOICE')
    y -= 30
    p.setFont('Helvetica', 10)
    p.drawString(50, y, f'Invoice #: {invoice.invoice_number}')
    p.drawString(300, y, f'Date: {invoice.date.strftime("%d-%m-%Y")}')
    y -= 20
    p.drawString(50, y, f'Customer: {invoice.customer_name}')
    p.drawString(300, y, f'GSTIN: {invoice.customer_gstin}')
    y -= 20
    p.drawString(50, y, f'Address: {invoice.customer_address}')
    y -= 30
    p.setFont('Helvetica-Bold', 10)
    p.drawString(50, y, 'No.')
    p.drawString(80, y, 'Product')
    p.drawString(180, y, 'HSN')
    p.drawString(230, y, 'Qty')
    p.drawString(270, y, 'Price')
    p.drawString(320, y, 'GST %')
    p.drawString(370, y, 'CGST')
    p.drawString(420, y, 'SGST')
    p.drawString(470, y, 'Total')
    y -= 15
    p.setFont('Helvetica', 10)
    for idx, item in enumerate(items, 1):
        p.drawString(50, y, str(idx))
        p.drawString(80, y, item.product.name)
        p.drawString(180, y, item.product.hsn_code)
        p.drawString(230, y, str(item.quantity))
        p.drawString(270, y, str(item.price))
        p.drawString(320, y, str(item.gst_percent))
        p.drawString(370, y, str(item.cgst))
        p.drawString(420, y, str(item.sgst))
        p.drawString(470, y, str(item.total))
        y -= 15
        if y < 100:
            p.showPage()
            y = height - 50
    y -= 10
    p.setFont('Helvetica-Bold', 10)
    p.drawString(320, y, 'Grand Total:')
    p.drawString(420, y, str(invoice.total))
    y -= 15
    p.drawString(320, y, 'Total CGST:')
    p.drawString(420, y, str(invoice.cgst))
    y -= 15
    p.drawString(320, y, 'Total SGST:')
    p.drawString(420, y, str(invoice.sgst))
    p.showPage()
    p.save()
    buffer.seek(0)
    _log_invoice_activity('Invoice PDF Downloaded', f'Invoice {invoice.invoice_number} PDF downloaded')
    return send_file(buffer, as_attachment=True, download_name=f'invoice_{invoice.invoice_number}.pdf', mimetype='application/pdf')


@invoices_bp.route('/<int:invoice_id>/print-track', methods=['POST'])
@login_required
def track_invoice_print(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    _log_invoice_activity('Invoice Print Clicked', f'Print clicked for invoice {invoice.invoice_number}')
    return ('', 204)

@invoices_bp.route('/<int:invoice_id>')
@login_required
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    payments = Payment.query.filter_by(invoice_id=invoice.id).order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    overpaid_amount = round(max(float(invoice.paid_amount or 0) - float(invoice.total or 0), 0.0), 2)
    can_receive_payment = _can_receive_payment(invoice)
    _log_invoice_activity(
        'Invoice Viewed',
        f'Invoice {invoice.invoice_number} viewed for customer {invoice.customer_name}',
    )
    items = invoice.items
    from models import Company
    company = Company.query.first()
    return render_template(
        'invoices/view.html',
        invoice=invoice,
        items=items,
        company=company,
        payments=payments,
        overpaid_amount=overpaid_amount,
        can_receive_payment=can_receive_payment,
    )


@invoices_bp.route('/<int:invoice_id>/receive-payment', methods=['GET', 'POST'])
@login_required
def receive_payment(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    can_manage_payments = _can_manage_payments()
    today = datetime.now().strftime('%Y-%m-%d')
    can_receive_payment = _can_receive_payment(invoice)

    if not can_receive_payment:
        flash('This invoice is already fully paid. Use Edit Payment only if you need to adjust an existing payment.', 'info')
        return redirect(url_for('invoices.view_invoice', invoice_id=invoice.id))

    if request.method == 'POST':
        amount = request.form.get('amount', type=float)
        payment_date_str = request.form.get('payment_date', '').strip()
        payment_mode = _normalize_payment_mode(request.form.get('payment_mode', '').strip())
        bank_account_id = request.form.get('bank_account_id', type=int)
        reference_no = request.form.get('reference_no', '').strip()
        notes = request.form.get('notes', '').strip()

        if not amount or amount <= 0:
            flash('Enter a valid payment amount.', 'danger')
            return redirect(url_for('invoices.receive_payment', invoice_id=invoice.id))
        if amount > (invoice.balance_amount or 0):
            flash('Payment amount cannot be greater than pending balance.', 'danger')
            return redirect(url_for('invoices.receive_payment', invoice_id=invoice.id))

        payment_date = datetime.now()
        if payment_date_str:
            try:
                payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Payment date format is invalid.', 'danger')
                return redirect(url_for('invoices.receive_payment', invoice_id=invoice.id))

        payment = Payment(
            invoice_id=invoice.id,
            amount=round(amount, 2),
            payment_date=payment_date,
            payment_mode=payment_mode or None,
            bank_account_id=bank_account_id if _is_non_cash_mode(payment_mode) else None,
            reference_no=reference_no or None,
            notes=notes or None,
            received_by=current_user.id,
        )
        db.session.add(payment)
        db.session.flush()
        _sync_invoice_payment_from_transactions(invoice)

        db.session.add(
            ActivityLog(
                user_id=current_user.id,
                username=current_user.username,
                action='Invoice Payment Received',
                details=(
                    f'Invoice {invoice.invoice_number} received payment={round(amount, 2)} '
                    f'mode={payment_mode or "-"} bank_account_id={bank_account_id or "-"} '
                    f'ref={reference_no or "-"} status={invoice.payment_status}'
                ),
            )
        )
        db.session.commit()
        if _is_non_cash_mode(payment_mode) and not payment.bank_account_id:
            flash('Payment saved without bank account linkage. Please map it later in Bank Book cleanup.', 'warning')
        flash('Payment recorded successfully.', 'success')
        return redirect(url_for('invoices.view_invoice', invoice_id=invoice.id))

    payments = Payment.query.filter_by(invoice_id=invoice.id).order_by(Payment.payment_date.desc(), Payment.id.desc()).all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).order_by(BankAccount.account_name.asc()).all()
    return render_template('invoices/receive_payment.html', invoice=invoice, payments=payments, today=today, can_manage_payments=can_manage_payments, bank_accounts=bank_accounts)


@invoices_bp.route('/payments/<int:payment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_payment(payment_id):
    invoice_id_hint = request.values.get('invoice_id', type=int)
    return_to = (request.values.get('return_to') or '').strip().lower()
    from_date = (request.values.get('from_date') or '').strip()
    to_date = (request.values.get('to_date') or '').strip()

    def _redirect_back_to_context(mapped_payment_id=None):
        if return_to == 'bank_book':
            route_args = {}
            if from_date:
                route_args['from_date'] = from_date
            if to_date:
                route_args['to_date'] = to_date
            if mapped_payment_id:
                route_args['recently_mapped_payment_id'] = mapped_payment_id
            return redirect(url_for('finance.bank_book', **route_args))
        return redirect(url_for('invoices.receive_payment', invoice_id=invoice.id))

    payment = Payment.query.get(payment_id)
    if payment is None:
        _log_invoice_activity(
            'Invoice Payment Edit Miss',
            f'Payment id={payment_id} not found during edit. Possibly already reversed/changed.',
        )
        flash('Payment is no longer available. It may have been reversed by another user.', 'warning')
        if return_to == 'bank_book':
            route_args = {}
            if from_date:
                route_args['from_date'] = from_date
            if to_date:
                route_args['to_date'] = to_date
            return redirect(url_for('finance.bank_book', **route_args))
        if invoice_id_hint:
            return redirect(url_for('invoices.receive_payment', invoice_id=invoice_id_hint))
        return redirect(url_for('invoices.crud_invoices'))
    invoice = Invoice.query.get_or_404(payment.invoice_id)

    if not _can_manage_payments():
        _log_invoice_activity(
            'Invoice Payment Edit Denied',
            f'Role {current_user.role} attempted payment edit: invoice={invoice.invoice_number}, {_payment_snapshot(payment)}',
        )
        flash('Only admin or approver can edit payments.', 'danger')
        return _redirect_back_to_context()

    if request.method == 'POST':
        amount = request.form.get('amount', type=float)
        payment_date_str = request.form.get('payment_date', '').strip()
        payment_mode = _normalize_payment_mode(request.form.get('payment_mode', '').strip())
        bank_account_id = request.form.get('bank_account_id', type=int)
        reference_no = request.form.get('reference_no', '').strip()
        notes = request.form.get('notes', '').strip()

        if not amount or amount <= 0:
            flash('Enter a valid payment amount.', 'danger')
            return redirect(request.url)

        paid_excluding_current = round(float(invoice.paid_amount or 0) - float(payment.amount or 0), 2)
        max_allowed = round(float(invoice.total or 0) - paid_excluding_current, 2)
        if amount > max_allowed:
            flash('Payment amount is too high for this invoice.', 'danger')
            return redirect(request.url)

        payment_date = payment.payment_date or datetime.now()
        if payment_date_str:
            try:
                payment_date = datetime.strptime(payment_date_str, '%Y-%m-%d')
            except ValueError:
                flash('Payment date format is invalid.', 'danger')
                return redirect(request.url)

        before_payment = _payment_snapshot(payment)
        before_invoice = _invoice_financial_snapshot(invoice)

        payment.amount = round(amount, 2)
        payment.payment_date = payment_date
        payment.payment_mode = payment_mode or None
        payment.bank_account_id = bank_account_id if _is_non_cash_mode(payment_mode) else None
        payment.reference_no = reference_no or None
        payment.notes = notes or None

        _sync_invoice_payment_from_transactions(invoice)
        after_payment = _payment_snapshot(payment)
        after_invoice = _invoice_financial_snapshot(invoice)

        db.session.add(
            ActivityLog(
                user_id=current_user.id,
                username=current_user.username,
                action='Invoice Payment Edited',
                details=(
                    f'Invoice {invoice.invoice_number} payment edited; '
                    f'before_payment=[{before_payment}] after_payment=[{after_payment}]; '
                    f'before_invoice=[{before_invoice}] after_invoice=[{after_invoice}]'
                ),
            )
        )
        db.session.commit()
        if _is_non_cash_mode(payment_mode) and not payment.bank_account_id:
            flash('Payment saved without bank account linkage. Please map it later in Bank Book cleanup.', 'warning')
            flash('Payment updated successfully.', 'success')
            return _redirect_back_to_context()

        flash('Payment mapped to bank account. Cleanup entry completed.', 'success')
        return _redirect_back_to_context(mapped_payment_id=payment.id)

    bank_accounts = BankAccount.query.filter_by(is_active=True).order_by(BankAccount.account_name.asc()).all()
    return render_template(
        'invoices/edit_payment.html',
        invoice=invoice,
        payment=payment,
        bank_accounts=bank_accounts,
        return_to=return_to,
        from_date=from_date,
        to_date=to_date,
    )


@invoices_bp.route('/payments/<int:payment_id>/reverse', methods=['POST'])
@login_required
def reverse_payment(payment_id):
    invoice_id_hint = request.values.get('invoice_id', type=int)
    payment = Payment.query.get(payment_id)
    if payment is None:
        _log_invoice_activity(
            'Invoice Payment Reverse Miss',
            f'Payment id={payment_id} not found during reversal. Possibly already reversed/changed.',
        )
        flash('Payment is already reversed or no longer available.', 'warning')
        if invoice_id_hint:
            return redirect(url_for('invoices.receive_payment', invoice_id=invoice_id_hint))
        return redirect(url_for('invoices.crud_invoices'))
    invoice = Invoice.query.get_or_404(payment.invoice_id)
    reversal_reason = request.form.get('reversal_reason', '').strip()

    if not _can_manage_payments():
        _log_invoice_activity(
            'Invoice Payment Reverse Denied',
            (
                f'Role {current_user.role} attempted payment reversal: '
                f'invoice={invoice.invoice_number}, {_payment_snapshot(payment)}, '
                f'reason={reversal_reason or "-"}'
            ),
        )
        flash('Only admin or approver can reverse payments.', 'danger')
        return redirect(url_for('invoices.receive_payment', invoice_id=invoice.id))

    if not reversal_reason:
        flash('Reversal reason is required.', 'danger')
        return redirect(url_for('invoices.receive_payment', invoice_id=invoice.id))

    before_payment = _payment_snapshot(payment)
    before_invoice = _invoice_financial_snapshot(invoice)
    invoice_number = invoice.invoice_number

    db.session.delete(payment)
    db.session.flush()
    _sync_invoice_payment_from_transactions(invoice)
    after_invoice = _invoice_financial_snapshot(invoice)

    db.session.add(
        ActivityLog(
            user_id=current_user.id,
            username=current_user.username,
            action='Invoice Payment Reversed',
            details=(
                f'Invoice {invoice_number} payment reversed; '
                f'removed_payment=[{before_payment}]; '
                f'before_invoice=[{before_invoice}] after_invoice=[{after_invoice}]; '
                f'reversal_reason={reversal_reason}'
            ),
        )
    )
    db.session.commit()
    flash('Payment reversed successfully.', 'success')
    return redirect(url_for('invoices.receive_payment', invoice_id=invoice.id))


def get_next_invoice_number():
	last_invoice = Invoice.query.order_by(Invoice.id.desc()).first()
	if last_invoice:
		try:
			return f"INV{int(last_invoice.invoice_number[3:]) + 1:05d}"
		except:
			return f"INV{last_invoice.id + 1:05d}"
	return "INV00001"


@invoices_bp.route('/', methods=['GET', 'POST'])
@login_required
def crud_invoices():
    edit_id = request.args.get('edit_id', type=int)
    form_invoice = None
    can_manage_invoices = _can_manage_invoices()
    products = Product.query.all()
    bank_accounts = BankAccount.query.filter_by(is_active=True).order_by(BankAccount.account_name.asc()).all()
    from models import Customer
    customers = Customer.query.order_by(Customer.name).all()
    if request.method == 'POST':
        # Delete
        delete_id = request.form.get('delete_id', type=int)
        if delete_id:
            if not can_manage_invoices:
                _log_invoice_activity(
                    'Invoice Delete Denied',
                    f'Role {current_user.role} attempted to delete invoice_id={delete_id}',
                )
                flash('Only admin or approver can delete invoices.', 'danger')
                return redirect(url_for('invoices.crud_invoices'))
            invoice = Invoice.query.get(delete_id)
            if invoice:
                invoice_number = invoice.invoice_number
                customer_name = invoice.customer_name
                # Delete items first
                InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()
                db.session.delete(invoice)
                db.session.add(
                    ActivityLog(
                        user_id=current_user.id,
                        username=current_user.username,
                        action='Invoice Deleted',
                        details=f'Invoice {invoice_number} deleted for customer {customer_name}',
                    )
                )
                db.session.commit()
                flash('Invoice deleted!', 'success')
            return redirect(url_for('invoices.crud_invoices'))
        # Add or Update
        iid = request.form.get('id', type=int)
        if iid and not can_manage_invoices:
            _log_invoice_activity(
                'Invoice Edit Denied',
                f'Role {current_user.role} attempted to edit invoice_id={iid}',
            )
            flash('Only admin or approver can edit invoices.', 'danger')
            return redirect(url_for('invoices.crud_invoices'))
        customer_id = request.form.get('customer_id', type=int)
        customer = Customer.query.get(customer_id) if customer_id else None
        customer_name = customer.name if customer else ''
        customer_gstin = customer.gstin if customer else ''
        customer_address = customer.address if customer else ''
        product_ids = request.form.getlist('product_id')
        quantities = request.form.getlist('quantity')
        items = []
        total = 0
        cgst = 0
        sgst = 0
        for i, product_id in enumerate(product_ids):
            product = Product.query.get(int(product_id))
            quantity = int(quantities[i])
            price = product.price
            gst_percent = product.gst_percent
            item_total = price * quantity
            item_gst = item_total * gst_percent / 100
            item_cgst = item_gst / 2
            item_sgst = item_gst / 2
            total += item_total + item_gst
            cgst += item_cgst
            sgst += item_sgst
            items.append({'product_id': product.id, 'quantity': quantity, 'price': price, 'gst_percent': gst_percent, 'cgst': item_cgst, 'sgst': item_sgst, 'total': item_total + item_gst})
        # Round totals to two decimals
        total = round(total, 2)
        cgst = round(cgst, 2)
        sgst = round(sgst, 2)

        payment_type = (request.form.get('billing_payment_type') or 'credit').strip().lower()
        payment_mode = _normalize_payment_mode((request.form.get('billing_payment_mode') or '').strip())
        payment_bank_account_id = request.form.get('billing_bank_account_id', type=int)
        reference_no = (request.form.get('billing_reference_no') or '').strip()
        payment_notes = (request.form.get('billing_payment_notes') or '').strip()
        amount_received_raw = (request.form.get('billing_amount_received') or '').strip()

        amount_received = 0.0
        if payment_type == 'pay_now':
            try:
                amount_received = round(float(amount_received_raw), 2)
            except (TypeError, ValueError):
                amount_received = 0.0

            if amount_received <= 0:
                flash('For Pay Now, enter a valid received amount.', 'danger')
                return redirect(url_for('invoices.crud_invoices'))
            if not payment_mode:
                flash('For Pay Now, select payment mode.', 'danger')
                return redirect(url_for('invoices.crud_invoices'))
            if payment_mode.lower() != 'cash' and amount_received > total:
                flash('For UPI/Card/Bank, received amount cannot exceed invoice total.', 'danger')
                return redirect(url_for('invoices.crud_invoices'))

        if iid:
            invoice = Invoice.query.get(iid)
            if invoice:
                invoice_number = invoice.invoice_number
                invoice.customer_name = customer_name
                invoice.customer_gstin = customer_gstin
                invoice.customer_address = customer_address
                invoice.total = total
                invoice.cgst = cgst
                invoice.sgst = sgst
                _recalculate_invoice_payment(invoice)
                overpaid_amount = round(float(invoice.paid_amount or 0) - float(invoice.total or 0), 2)
                # Remove old items
                InvoiceItem.query.filter_by(invoice_id=invoice.id).delete()
                db.session.flush()
                for item in items:
                    db.session.add(InvoiceItem(invoice_id=invoice.id, **item))
                db.session.add(
                    ActivityLog(
                        user_id=current_user.id,
                        username=current_user.username,
                        action='Invoice Updated',
                        details=f'Invoice {invoice_number} updated for customer {customer_name}',
                    )
                )
                db.session.commit()
                if overpaid_amount > 0:
                    flash(
                        f'Invoice updated. Collected amount now exceeds the revised total by {overpaid_amount:.2f}.',
                        'warning',
                    )
                flash('Invoice updated!', 'success')
        else:
            applied_amount = 0.0
            change_returned = 0.0
            if payment_type == 'pay_now':
                applied_amount = round(min(amount_received, total), 2)
                if payment_mode.lower() == 'cash':
                    change_returned = round(amount_received - applied_amount, 2)

            invoice = Invoice(
                invoice_number=get_next_invoice_number(),
                customer_name=customer_name,
                customer_gstin=customer_gstin,
                customer_address=customer_address,
                date=datetime.now(),
                total=total,
                cgst=cgst,
                sgst=sgst,
                paid_amount=0,
                balance_amount=total,
                payment_status='unpaid',
                user_id=current_user.id
            )
            db.session.add(invoice)
            db.session.flush()
            for item in items:
                db.session.add(InvoiceItem(invoice_id=invoice.id, **item))

            if payment_type == 'pay_now' and applied_amount > 0:
                bill_time_notes = payment_notes
                bill_time_meta = f'bill_time_received={amount_received:.2f}; change_returned={change_returned:.2f}'
                if bill_time_notes:
                    bill_time_notes = f'{bill_time_notes} | {bill_time_meta}'
                else:
                    bill_time_notes = bill_time_meta

                payment = Payment(
                    invoice_id=invoice.id,
                    amount=applied_amount,
                    payment_date=datetime.now(),
                    payment_mode=payment_mode,
                    bank_account_id=payment_bank_account_id if _is_non_cash_mode(payment_mode) else None,
                    reference_no=reference_no or None,
                    notes=bill_time_notes,
                    received_by=current_user.id,
                )
                db.session.add(payment)
                db.session.flush()
                _sync_invoice_payment_from_transactions(invoice)

            db.session.add(
                ActivityLog(
                    user_id=current_user.id,
                    username=current_user.username,
                    action='Invoice Created',
                    details=(
                        f'Invoice {invoice.invoice_number} created for customer {customer_name}; '
                        f'payment_type={payment_type}; '
                        f'amount_received={round(amount_received, 2)}; '
                        f'applied={round(applied_amount, 2)}; '
                        f'change_returned={round(change_returned, 2)}; '
                        f'payment_mode={payment_mode or "-"}; '
                        f'payment_bank_account_id={payment_bank_account_id or "-"}; '
                        f'reference={reference_no or "-"}; '
                        f'status={invoice.payment_status}'
                    ),
                )
            )
            db.session.commit()
            if payment_type == 'pay_now':
                if _is_non_cash_mode(payment_mode) and not payment_bank_account_id:
                    flash('Non-cash bill-time payment saved without bank account linkage. Map it later in Bank Book cleanup.', 'warning')
                flash(
                    (
                        f'Invoice added. Received: {amount_received:.2f}, '
                        f'Applied: {applied_amount:.2f}, '
                        f'Change Returned: {change_returned:.2f}.'
                    ),
                    'success',
                )
            else:
                flash('Invoice added!', 'success')
        return redirect(url_for('invoices.crud_invoices'))
    # GET
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    if not from_date and not to_date:
        today = datetime.now().strftime('%Y-%m-%d')
        from_date = to_date = today
    search = request.args.get('search', '')
    query = Invoice.query
    if from_date:
        query = query.filter(func.date(Invoice.date) >= from_date)
    if to_date:
        query = query.filter(func.date(Invoice.date) <= to_date)
    if search:
        query = query.filter(
            Invoice.invoice_number.ilike(f'%{search}%') |
            Invoice.customer_name.ilike(f'%{search}%')
        )
    if edit_id and not can_manage_invoices:
        _log_invoice_activity(
            'Invoice Edit Denied',
            f'Role {current_user.role} attempted to access edit form for invoice_id={edit_id}',
        )
        flash('Only admin or approver can edit invoices.', 'danger')
        return redirect(url_for('invoices.crud_invoices'))
    if edit_id:
        form_invoice = Invoice.query.get(edit_id)
    invoices = query.order_by(Invoice.created_at.desc() if hasattr(Invoice, 'created_at') else Invoice.date.desc()).all()
    return render_template('invoices/crud.html', invoices=invoices, form_invoice=form_invoice, products=products, customers=customers, bank_accounts=bank_accounts, from_date=from_date, to_date=to_date, search=search, can_manage_invoices=can_manage_invoices)