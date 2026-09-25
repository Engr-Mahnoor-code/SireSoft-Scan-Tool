from django import forms


def _input(**attrs):
    return forms.TextInput(attrs={'class': 'form-input', **attrs})


def _number(**attrs):
    return forms.NumberInput(
        attrs={'class': 'form-input', 'step': 'any', **attrs})


class EstablishmentForm(forms.Form):
    name = forms.CharField(max_length=255, required=False, widget=_input())
    date = forms.CharField(max_length=100, required=False, widget=_input())
    time = forms.CharField(max_length=50, required=False, widget=_input())
    address = forms.CharField(
        max_length=500, required=False,
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 2}))


class ItemForm(forms.Form):
    name = forms.CharField(max_length=255, widget=_input(placeholder='Item'))
    quantity = forms.FloatField(
        required=False, min_value=0, widget=_number(placeholder='1'))
    unit_price = forms.FloatField(required=False, widget=_number())
    total = forms.FloatField(required=False, widget=_number())


ItemFormSet = forms.formset_factory(
    ItemForm, extra=0, can_delete=True, max_num=200, validate_max=True)


class BillSummaryForm(forms.Form):
    subtotal = forms.FloatField(required=False, widget=_number())
    tax = forms.FloatField(required=False, widget=_number())
    discount = forms.FloatField(required=False, widget=_number())
    tip = forms.FloatField(required=False, widget=_number())
    grand_total = forms.FloatField(required=False, widget=_number())
    payment_method = forms.CharField(
        max_length=100, required=False, widget=_input())


class InsightsForm(forms.Form):
    insights = forms.CharField(
        required=False,
        help_text='One insight per line.',
        widget=forms.Textarea(attrs={'class': 'form-input', 'rows': 4}))


class ReceiptEditForms:
    """
    The four forms behind the edit page, bound and saved together.

    `extracted_data` is the one source the detail page reads, so an edit
    rewrites it in the same shape the worker produces; keys this page does not
    know about are carried over untouched.
    """

    prefixes = ('est', 'items', 'bill', 'notes')

    def __init__(self, receipt, data=None):
        self.receipt = receipt
        stored = receipt.extracted_data or {}
        items = [i for i in stored.get('items') or [] if isinstance(i, dict)]
        self.establishment = EstablishmentForm(
            data, prefix='est', initial=stored.get('establishment') or {})
        self.items = ItemFormSet(data, prefix='items', initial=items)
        self.bill = BillSummaryForm(
            data, prefix='bill', initial=stored.get('bill_summary') or {})
        self.notes = InsightsForm(data, prefix='notes', initial={
            'insights': '\n'.join(str(i) for i in stored.get('insights') or [])})

    def is_valid(self):
        # Every form is validated so each one carries its own errors.
        results = [f.is_valid() for f in
                   (self.establishment, self.items, self.bill, self.notes)]
        return all(results)

    def cleaned_data(self):
        stored = dict(self.receipt.extracted_data or {})

        establishment = dict(stored.get('establishment') or {})
        establishment.update(
            {k: v.strip() for k, v in self.establishment.cleaned_data.items()})

        items = []
        for form in self.items.forms:
            row = form.cleaned_data
            if not row or row.get('DELETE') or not row.get('name', '').strip():
                continue
            items.append({
                'name': row['name'].strip(),
                'quantity': row.get('quantity') or 1.0,
                'unit_price': row.get('unit_price') or 0.0,
                'total': row.get('total') or 0.0,
            })

        bill = dict(stored.get('bill_summary') or {})
        for key, value in self.bill.cleaned_data.items():
            if key == 'payment_method':
                bill[key] = value.strip()
            else:
                bill[key] = value or 0.0

        insights = [line.strip() for line in
                    self.notes.cleaned_data['insights'].splitlines()
                    if line.strip()]

        stored.update({
            'establishment': establishment,
            'items': items,
            'bill_summary': bill,
            'insights': insights,
        })
        return stored
