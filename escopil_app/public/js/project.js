frappe.ui.form.on('Project', {
	refresh(frm) {
		if (frm.is_new()) {
			return;
		}

		frm.add_custom_button(__('Painel de Orçamento'), () => {
			frappe.route_options = { project: frm.doc.name };
			frappe.set_route('project-dashboard');
		});

		frappe.require('/assets/escopil_app/css/project_dashboard.css', () => {
			render_budget_entries_section(frm);
		});
	}
});

function render_budget_entries_section(frm) {
	frm.dashboard.parent.find('.pd-embedded-entries').remove();

	frm.dashboard.add_section(
		'<div class="project-dashboard pd-embedded-entries pd-embedded-entries-costs"></div>',
		__('Custos do Projeto')
	);
	const $costs_wrapper = frm.dashboard.parent.find('.pd-embedded-entries-costs');

	frm.dashboard.add_section(
		'<div class="project-dashboard pd-embedded-entries pd-embedded-entries-billing"></div>',
		__('Faturação do Projeto')
	);
	const $billing_wrapper = frm.dashboard.parent.find('.pd-embedded-entries-billing');

	new ProjectEntryTable({
		frm,
		wrapper: $costs_wrapper,
		doctype: 'Project Cost Entry',
		add_label: __('Adicionar Custo'),
		order_by: 'posting_date desc',
		lock_field: 'is_auto_generated',
		columns: [
			{ fieldname: 'rubrica', label: __('Rubrica') },
			{ fieldname: 'posting_date', label: __('Data'), format: (v) => frappe.datetime.str_to_user(v) },
			{ fieldname: 'amount', label: __('Valor'), format: (v) => format_currency(v) },
			{ fieldname: 'source_type', label: __('Origem') },
		],
		dialog_fields: [
			{ fieldname: 'rubrica', fieldtype: 'Link', options: 'Project Rubrica', label: __('Rubrica'), reqd: 1 },
			{ fieldname: 'posting_date', fieldtype: 'Date', label: __('Data'), reqd: 1, default: frappe.datetime.get_today() },
			{ fieldname: 'amount', fieldtype: 'Currency', label: __('Valor'), reqd: 1 },
			{ fieldname: 'remarks', fieldtype: 'Small Text', label: __('Observações') },
		],
		default_values: { source_type: 'Manual' },
	});

	new ProjectEntryTable({
		frm,
		wrapper: $billing_wrapper,
		doctype: 'Project Billing Entry',
		add_label: __('Adicionar Faturação'),
		order_by: 'month desc',
		columns: [
			{ fieldname: 'month', label: __('Mês'), format: (v) => frappe.datetime.str_to_user(v) },
			{ fieldname: 'billable_amount', label: __('Valor a Cobrar'), format: (v) => format_currency(v) },
		],
		dialog_fields: [
			{ fieldname: 'month', fieldtype: 'Date', label: __('Mês'), reqd: 1, default: frappe.datetime.get_today() },
			{ fieldname: 'billable_amount', fieldtype: 'Currency', label: __('Valor a Cobrar'), reqd: 1 },
			{ fieldname: 'remarks', fieldtype: 'Small Text', label: __('Observações') },
		],
	});
}

class ProjectEntryTable {
	constructor({ frm, wrapper, doctype, add_label, columns, dialog_fields, default_values, order_by, lock_field }) {
		this.frm = frm;
		this.doctype = doctype;
		this.columns = columns;
		this.dialog_fields = dialog_fields;
		this.default_values = default_values || {};
		this.order_by = order_by || 'creation desc';
		this.lock_field = lock_field;

		this.$wrapper = $(`
			<div class="pd-entry-block">
				<div class="pd-entry-head">
					<button class="pd-entry-add" type="button">+ ${frappe.utils.escape_html(add_label)}</button>
				</div>
				<div class="pd-entry-table-wrap"></div>
			</div>
		`).appendTo(wrapper);

		this.$wrapper.find('.pd-entry-add').on('click', () => this.open_dialog());
		this.reload();
	}

	reload() {
		const fields = this.columns.map((c) => c.fieldname).concat(['name']);
		if (this.lock_field) {
			fields.push(this.lock_field);
		}
		frappe.db
			.get_list(this.doctype, {
				filters: { project: this.frm.doc.name },
				fields,
				order_by: this.order_by,
				limit_page_length: 0,
			})
			.then((rows) => this.render(rows));
	}

	render(rows) {
		const $body = this.$wrapper.find('.pd-entry-table-wrap');
		if (!rows.length) {
			$body.html('<div class="pd-empty pd-empty-inline">Sem lançamentos.</div>');
			return;
		}

		const head = this.columns.map((c) => `<th class="text-right">${frappe.utils.escape_html(c.label)}</th>`).join('');
		const body = rows
			.map((row) => {
				const locked = this.lock_field && row[this.lock_field] ? ' pd-row-locked' : '';
				const cells = this.columns
					.map((c) => {
						const v = c.format ? c.format(row[c.fieldname]) : row[c.fieldname] || '';
						return `<td class="text-right">${frappe.utils.escape_html(String(v))}</td>`;
					})
					.join('');
				return `<tr class="pd-entry-row${locked}" data-name="${frappe.utils.escape_html(row.name)}">${cells}</tr>`;
			})
			.join('');

		$body.html(`
			<table class="pd-ledger pd-ledger-compact">
				<thead><tr>${head}</tr></thead>
				<tbody>${body}</tbody>
			</table>
		`);

		$body.find('.pd-entry-row').on('click', (e) => {
			const $row = $(e.currentTarget);
			if ($row.hasClass('pd-row-locked')) {
				frappe.show_alert({
					message: __('Lançamento gerado automaticamente a partir de uma Fatura de Compra — não pode ser editado aqui.'),
					indicator: 'orange',
				});
				return;
			}
			this.open_dialog($row.data('name'));
		});
	}

	open_dialog(name) {
		const is_new = !name;
		const dialog = new frappe.ui.Dialog({
			title: is_new ? __('Novo Lançamento') : __('Editar Lançamento'),
			fields: this.dialog_fields,
			primary_action_label: is_new ? __('Adicionar') : __('Guardar'),
			primary_action: (values) => {
				const action = is_new
					? frappe.call({
							method: 'frappe.client.insert',
							args: {
								doc: Object.assign({}, this.default_values, values, {
									doctype: this.doctype,
									project: this.frm.doc.name,
								}),
							},
					  })
					: frappe.call({
							method: 'frappe.client.set_value',
							args: { doctype: this.doctype, name, fieldname: values },
					  });

				action.then(() => {
					dialog.hide();
					this.reload();
				});
			},
		});

		if (!is_new) {
			frappe.db.get_doc(this.doctype, name).then((doc) => dialog.set_values(doc));
		}

		dialog.show();
	}
}
