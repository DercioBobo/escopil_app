frappe.pages['project-dashboard'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Project Dashboard',
		single_column: true
	});

	frappe.require('/assets/escopil_app/css/project_dashboard.css', () => {
		frappe.project_dashboard = new ProjectDashboard(page);
	});
};

frappe.pages['project-dashboard'].on_page_show = function () {
	if (frappe.project_dashboard) {
		frappe.project_dashboard.check_route_options();
	}
};

class ProjectDashboard {
	constructor(page) {
		this.page = page;
		this.setup();
	}

	setup() {
		$(this.page.body).html(`
			<div class="project-dashboard">
				<div class="pd-filter-bar"></div>
				<div class="pd-content"></div>
			</div>
		`);

		this.$wrapper = $(this.page.body).find('.project-dashboard');
		this.$content = this.$wrapper.find('.pd-content');

		this.project_control = frappe.ui.form.make_control({
			parent: this.$wrapper.find('.pd-filter-bar').get(0),
			df: {
				fieldtype: 'Link',
				fieldname: 'project',
				label: 'Projeto',
				options: 'Project',
				get_query: () => ({ filters: { custom_cost_control_enabled: 1 } }),
				onchange: () => {
					const project = this.project_control.get_value();
					if (project) {
						this.load(project);
					} else {
						this.render_empty();
					}
				}
			},
			render_input: true,
		});
		this.project_control.refresh();

		this.page.add_inner_button(__('Voltar ao Projeto'), () => {
			const project = this.project_control.get_value();
			if (project) {
				frappe.set_route('Form', 'Project', project);
			} else {
				window.history.back();
			}
		});

		this.page.add_inner_button(__('Atualizar'), () => {
			const project = this.project_control.get_value();
			if (project) {
				this.load(project);
			}
		});

		if (!this.check_route_options()) {
			this.render_empty();
		}
	}

	// consumes frappe.route_options.project so a "Painel de Orçamento" button
	// on the Project form can deep-link straight into this page
	check_route_options() {
		const options = frappe.route_options;
		if (options && options.project) {
			frappe.route_options = null;
			this.project_control.set_value(options.project);
			return true;
		}
		return false;
	}

	render_empty() {
		this.$content.html(`
			<div class="pd-empty">Selecione um Projeto para ver o painel de orçamento.</div>
		`);
	}

	load(project) {
		this.project = project;
		frappe.call({
			method: 'escopil_app.project_management.page.project_dashboard.project_dashboard.get_dashboard_data',
			args: { project },
			freeze: true,
			callback: (r) => {
				if (r.message) {
					this.render(r.message);
				}
			}
		});
	}

	// variance = actual vs. the rubrica's own monthly forecast; class carries
	// how far under/over budget the cell is, alpha scales with severity
	variance_class(actual, forecast) {
		if (!forecast) {
			return actual ? { cls: 'pd-variance-over', alpha: 0.16 } : { cls: '', alpha: 0 };
		}
		const ratio = actual / forecast;
		if (ratio <= 0.9) {
			const severity = Math.min((0.9 - ratio) / 0.9, 1);
			return { cls: 'pd-variance-under', alpha: 0.08 + severity * 0.18 };
		}
		if (ratio > 1.1) {
			const severity = Math.min((ratio - 1.1) / 1.1, 1);
			return { cls: 'pd-variance-over', alpha: 0.08 + severity * 0.22 };
		}
		return { cls: '', alpha: 0 };
	}

	// billing variance is inverted vs. cost variance: meeting/exceeding the
	// monthly billing target is good (green), falling short is bad (rust)
	billing_variance_class(actual, forecast) {
		if (!forecast) {
			return actual ? { cls: 'pd-variance-under', alpha: 0.16 } : { cls: '', alpha: 0 };
		}
		const ratio = actual / forecast;
		if (ratio >= 1.1) {
			const severity = Math.min((ratio - 1.1) / 1.1, 1);
			return { cls: 'pd-variance-under', alpha: 0.08 + severity * 0.18 };
		}
		if (ratio < 0.9) {
			const severity = Math.min((0.9 - ratio) / 0.9, 1);
			return { cls: 'pd-variance-over', alpha: 0.08 + severity * 0.22 };
		}
		return { cls: '', alpha: 0 };
	}

	render(data) {
		const fmt = (v) => format_currency(v || 0);
		const pct = (v) => (v || 0).toFixed(1) + '%';
		const months = data.months;
		const n_months = months.length || 1;

		this._data = data;
		this._month_labels = {};
		months.forEach((m) => { this._month_labels[m.key] = m.label; });

		const total_cost = months.reduce((s, m) => s + (data.totals[m.key] || 0), 0);
		const total_committed = months.reduce((s, m) => s + (data.committed[m.key] || 0), 0);
		const total_billing = months.reduce((s, m) => s + (data.billing[m.key] || 0), 0);
		const total_billing_forecast = months.reduce((s, m) => s + (data.billing_forecast[m.key] || 0), 0);
		const total_margin = total_billing - total_cost;
		const total_margin_pct = total_billing ? (total_margin / total_billing * 100) : 0;
		const budget_total = (data.total_forecast || 0) * n_months;

		const strip = `
			<div class="pd-strip">
				<div class="pd-stat">
					<span class="pd-stat-label">Orçamento do Período</span>
					<span class="pd-stat-value">${fmt(budget_total)}</span>
					<span class="pd-stat-sub">${fmt(data.total_forecast)} / mês</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Custos Reais</span>
					<span class="pd-stat-value">${fmt(total_cost)}</span>
					<span class="pd-stat-sub">${budget_total ? pct(total_cost / budget_total * 100) : '—'} do orçamento</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Custos Comprometidos</span>
					<span class="pd-stat-value">${fmt(total_committed)}</span>
					<span class="pd-stat-sub">Encomendado c/ IVA, ainda não faturado</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Previsão de Faturação</span>
					<span class="pd-stat-value">${fmt(total_billing_forecast)}</span>
					<span class="pd-stat-sub">&nbsp;</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Valor Faturado</span>
					<span class="pd-stat-value">${fmt(total_billing)}</span>
					<span class="pd-stat-sub">${total_billing_forecast ? pct(total_billing / total_billing_forecast * 100) : '—'} da previsão</span>
				</div>
				<div class="pd-stat">
					<span class="pd-stat-label">Margem</span>
					<span class="pd-stat-value ${total_margin >= 0 ? 'is-positive' : 'is-negative'}">${fmt(total_margin)}</span>
					<span class="pd-stat-sub">${pct(total_margin_pct)}</span>
				</div>
			</div>
		`;

		const head = `
			<tr>
				<th class="pd-col-rubrica">Rubrica</th>
				<th class="text-right">Previsão Mensal</th>
				<th class="text-right">Peso</th>
				${months.map(m => `<th class="text-right">${frappe.utils.escape_html(m.label)}</th>`).join('')}
			</tr>
		`;

		const body = data.rubricas.map(r => `
			<tr>
				<td class="pd-col-rubrica">${frappe.utils.escape_html(r.rubrica)}</td>
				<td class="text-right">${fmt(r.monthly_forecast)}</td>
				<td class="text-right">
					<div class="pd-weight">
						<span>${pct(r.weight * 100)}</span>
						<span class="pd-weight-bar"><span style="width:${Math.min(r.weight * 100, 100)}%"></span></span>
					</div>
				</td>
				${months.map(m => {
					const actual = r.actuals[m.key] || 0;
					const committed = (r.committed && r.committed[m.key]) || 0;
					const v = this.variance_class(actual, r.monthly_forecast);
					const style = v.cls ? ` style="--pd-alpha:${v.alpha}"` : '';
					const committed_sub = committed
						? `<span class="pd-cell-committed pd-drill-committed" data-month="${m.key}" data-rubrica="${frappe.utils.escape_html(r.rubrica)}">+${fmt(committed)} comp.</span>`
						: '';
					const cls = `text-right ${v.cls}${actual ? ' pd-drill' : ''}`.trim();
					const drill = actual
						? ` data-kind="cost" data-month="${m.key}" data-rubrica="${frappe.utils.escape_html(r.rubrica)}"`
						: '';
					return `<td class="${cls}"${drill}${style}>${fmt(actual)}${committed_sub}</td>`;
				}).join('')}
			</tr>
		`).join('');

		const total_row = `
			<tr class="pd-row-total">
				<td class="pd-col-rubrica text-left" colspan="3">Total de Custos</td>
				${months.map(m => {
					const val = data.totals[m.key] || 0;
					const cls = val ? 'text-right pd-drill' : 'text-right';
					const drill = val ? ` data-kind="cost_total" data-month="${m.key}"` : '';
					return `<td class="${cls}"${drill}>${fmt(data.totals[m.key])}</td>`;
				}).join('')}
			</tr>
		`;

		const committed_row = `
			<tr class="pd-row-committed">
				<td class="text-left" colspan="3">Custos Comprometidos</td>
				${months.map(m => {
					const val = data.committed[m.key] || 0;
					const cls = val ? 'text-right pd-drill' : 'text-right';
					const drill = val ? ` data-kind="committed" data-month="${m.key}"` : '';
					return `<td class="${cls}"${drill}>${fmt(data.committed[m.key])}</td>`;
				}).join('')}
			</tr>
		`;

		const billing_forecast_row = `
			<tr class="pd-row-billing-forecast">
				<td class="text-left" colspan="3">Valor a Cobrar</td>
				${months.map(m => `<td class="text-right pd-drill-calc" data-kind="billing_forecast" data-month="${m.key}">${fmt(data.billing_forecast[m.key])}</td>`).join('')}
			</tr>
		`;

		const billing_row = `
			<tr class="pd-row-billing">
				<td class="text-left" colspan="3">Valor Faturado</td>
				${months.map(m => {
					const actual = data.billing[m.key] || 0;
					const v = this.billing_variance_class(actual, data.billing_forecast[m.key]);
					const style = v.cls ? ` style="--pd-alpha:${v.alpha}"` : '';
					const cls = `text-right ${v.cls}${actual ? ' pd-drill' : ''}`.trim();
					const drill = actual ? ` data-kind="billing" data-month="${m.key}"` : '';
					return `<td class="${cls}"${drill}${style}>${fmt(actual)}</td>`;
				}).join('')}
			</tr>
		`;

		const margin_row = `
			<tr class="pd-row-margin">
				<td class="text-left" colspan="3">Margem</td>
				${months.map(m => {
					const margin = data.margin[m.key] || 0;
					const cls = margin > 0 ? 'pd-variance-under' : (margin < 0 ? 'pd-variance-over' : '');
					const drillable = (data.billing[m.key] || data.totals[m.key]) ? ' pd-drill-calc' : '';
					const drill = drillable ? ` data-kind="margin" data-month="${m.key}"` : '';
					return `<td class="text-right ${cls}${drillable}"${drill}>${fmt(margin)}</td>`;
				}).join('')}
			</tr>
		`;

		const margin_pct_row = `
			<tr class="pd-row-margin-pct">
				<td class="text-left" colspan="3">Margem %</td>
				${months.map(m => {
					const v = data.margin_pct[m.key] || 0;
					const cls = v > 0 ? 'pd-variance-under' : (v < 0 ? 'pd-variance-over' : '');
					const drillable = (data.billing[m.key] || data.totals[m.key]) ? ' pd-drill-calc' : '';
					const drill = drillable ? ` data-kind="margin_pct" data-month="${m.key}"` : '';
					return `<td class="text-right ${cls}${drillable}"${drill}>${pct(v)}</td>`;
				}).join('')}
			</tr>
		`;

		this.$content.html(`
			<div class="pd-fade">
				${strip}
				<h6 class="pd-eyebrow">Rubricas do Orçamento</h6>
				<div class="pd-table-wrap">
					<table class="pd-ledger">
						<thead>${head}</thead>
						<tbody>${body}${total_row}${committed_row}${billing_forecast_row}${billing_row}${margin_row}${margin_pct_row}</tbody>
					</table>
				</div>
			</div>
		`);

		this.$content.find('td.pd-drill').on('click', (e) => {
			const $td = $(e.currentTarget);
			this.show_breakdown($td.attr('data-kind'), $td.attr('data-month'), $td.attr('data-rubrica') || null);
		});

		// the "+X comp." note drills the committed value for that one rubrica,
		// not the whole month — stop the click reaching the cost cell behind it
		this.$content.find('.pd-drill-committed').on('click', (e) => {
			e.stopPropagation();
			const $s = $(e.currentTarget);
			this.show_breakdown('committed', $s.attr('data-month'), $s.attr('data-rubrica'));
		});

		// derived cells (a cobrar / margem / margem %) have no source docs —
		// clicking them shows how the number is computed
		this.$content.find('td.pd-drill-calc').on('click', (e) => {
			const $td = $(e.currentTarget);
			this.show_computation($td.attr('data-kind'), $td.attr('data-month'));
		});
	}

	show_computation(kind, month) {
		const data = this._data;
		if (!data) return;
		const fmt = (v) => format_currency(v || 0);
		const pct = (v) => (v || 0).toFixed(1) + '%';
		const ml = (this._month_labels && this._month_labels[month]) || month;

		let title;
		let lines;
		let result;

		if (kind === 'billing_forecast') {
			const is_override = data.billing_forecast_is_override && data.billing_forecast_is_override[month];
			title = `${__('Valor a Cobrar')} · ${ml}`;
			lines = [[__('Previsão mensal padrão (do Projeto)'), fmt(data.billing_forecast_default)]];
			if (is_override) {
				lines.push([__('Ajuste mensal para {0}', [ml]), fmt(data.billing_forecast[month])]);
			}
			lines.push([__('Aplicado a este mês'), is_override ? __('Ajuste mensal') : __('Valor padrão')]);
			result = [__('Valor a Cobrar'), fmt(data.billing_forecast[month])];
		} else if (kind === 'margin') {
			title = `${__('Margem')} · ${ml}`;
			lines = [
				[__('Valor Faturado'), fmt(data.billing[month])],
				[__('(−) Custos Reais'), fmt(data.totals[month])],
			];
			result = [__('Margem'), fmt(data.margin[month])];
		} else if (kind === 'margin_pct') {
			title = `${__('Margem %')} · ${ml}`;
			lines = [
				[__('Margem'), fmt(data.margin[month])],
				[__('(÷) Valor Faturado'), fmt(data.billing[month])],
			];
			result = [__('Margem %'), pct(data.margin_pct[month])];
		} else {
			return;
		}

		const body = lines.map(([label, value]) => `
			<tr>
				<td class="text-left">${frappe.utils.escape_html(label)}</td>
				<td class="text-right">${frappe.utils.escape_html(String(value))}</td>
			</tr>`).join('');

		const dialog = new frappe.ui.Dialog({
			title,
			fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
		});
		this._solidify_modal(dialog);
		dialog.fields_dict.body.$wrapper.html(`
			<div class="project-dashboard pd-breakdown">
				<div class="pd-breakdown-scroll">
					<table class="pd-ledger pd-ledger-compact pd-breakdown-table">
						<tbody>${body}</tbody>
						<tfoot>
							<tr class="pd-row-total">
								<td class="text-left">${frappe.utils.escape_html(result[0])}</td>
								<td class="text-right">${frappe.utils.escape_html(String(result[1]))}</td>
							</tr>
						</tfoot>
					</table>
				</div>
			</div>
		`);
		dialog.show();
	}

	// some themes leave .modal-content / .modal-body transparent, which lets the
	// ledger behind bleed through the breakdown table — force an opaque surface
	_solidify_modal(dialog) {
		dialog.$wrapper
			.find('.modal-content, .modal-body')
			.css('background-color', 'var(--card-bg, var(--bg-color, #fff))');
	}

	show_breakdown(kind, month, rubrica) {
		frappe.call({
			method: 'escopil_app.project_management.page.project_dashboard.project_dashboard.get_cell_breakdown',
			args: { project: this.project, kind, month: `${month}-01`, rubrica },
			freeze: true,
			callback: (r) => {
				if (r.message) {
					this.render_breakdown_dialog(kind, month, rubrica, r.message);
				}
			},
		});
	}

	render_breakdown_dialog(kind, month, rubrica, payload) {
		const fmt = (v) => format_currency(v || 0);
		const KIND_LABEL = {
			cost: __('Custos'),
			cost_total: __('Total de Custos'),
			billing: __('Valor Faturado'),
			committed: __('Custos Comprometidos'),
		};
		const month_label = (this._month_labels && this._month_labels[month]) || month;
		const title = [KIND_LABEL[kind] || kind, rubrica, month_label].filter(Boolean).join(' · ');
		const show_rubrica = kind === 'cost_total';
		const party_label = kind === 'billing' ? __('Cliente') : __('Fornecedor');
		const rows = payload.rows || [];
		const span = show_rubrica ? 5 : 4;

		let table;
		if (!rows.length) {
			table = `<div class="pd-empty pd-empty-inline">${__('Sem lançamentos.')}</div>`;
		} else {
			const tbody = rows.map((row) => {
				const doc_cell = row.docname
					? `<a class="pd-drill-link" data-doctype="${frappe.utils.escape_html(row.doctype || '')}" data-docname="${frappe.utils.escape_html(row.docname)}">${frappe.utils.escape_html(row.docname)}</a>`
					: __('Manual');
				const note = row.note
					? `<tr class="pd-note-row"><td colspan="${span + 1}">${frappe.utils.escape_html(row.note)}</td></tr>`
					: '';
				return `
					<tr>
						<td class="text-left">${frappe.datetime.str_to_user(row.date)}</td>
						${show_rubrica ? `<td class="text-left">${frappe.utils.escape_html(row.rubrica || '')}</td>` : ''}
						<td class="text-left">${doc_cell}</td>
						<td class="text-left">${frappe.utils.escape_html(row.party || '')}</td>
						<td class="text-left">${frappe.utils.escape_html(row.origem || '')}</td>
						<td class="text-right">${fmt(row.amount)}</td>
					</tr>${note}`;
			}).join('');

			table = `
				<table class="pd-ledger pd-ledger-compact pd-breakdown-table">
					<thead>
						<tr>
							<th class="text-left">${__('Data')}</th>
							${show_rubrica ? `<th class="text-left">${__('Rubrica')}</th>` : ''}
							<th class="text-left">${__('Documento')}</th>
							<th class="text-left">${party_label}</th>
							<th class="text-left">${__('Origem')}</th>
							<th class="text-right">${__('Valor')}</th>
						</tr>
					</thead>
					<tbody>${tbody}</tbody>
					<tfoot>
						<tr class="pd-row-total">
							<td class="text-left" colspan="${span}">${__('Total')}</td>
							<td class="text-right">${fmt(payload.total)}</td>
						</tr>
					</tfoot>
				</table>`;
		}

		const dialog = new frappe.ui.Dialog({
			title,
			size: 'large',
			fields: [{ fieldtype: 'HTML', fieldname: 'body' }],
		});
		this._solidify_modal(dialog);
		dialog.fields_dict.body.$wrapper.html(`<div class="project-dashboard pd-breakdown"><div class="pd-breakdown-scroll">${table}</div></div>`);
		dialog.$wrapper.find('.pd-drill-link').on('click', (e) => {
			const $a = $(e.currentTarget);
			frappe.set_route('Form', $a.data('doctype'), $a.data('docname'));
			dialog.hide();
		});
		dialog.show();
	}
}
