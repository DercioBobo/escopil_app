frappe.pages['next-ai'].on_page_load = function (wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Next AI',
		single_column: true,
	});

	frappe.require('/assets/escopil_app/css/next_ai.css', () => {
		frappe.next_ai = new NextAI(page);
	});
};

const SECTION_META = {
	invoicing: { label: 'Faturação', ready: true },
	purchasing: { label: 'Compras', ready: false },
	stock: { label: 'Stock', ready: false },
	projects: { label: 'Projetos', ready: true },
};
const SECTION_ORDER = ['invoicing', 'purchasing', 'stock', 'projects'];

// Caption shown above the live entity-search results in the typeahead
// dropdown, per section (see SEARCH_CONFIG server-side).
const SECTION_ENTITY_LABEL = {
	invoicing: 'Clientes',
	projects: 'Projetos',
};

// When the assistant is "focused" on a specific entity (a customer, later a
// supplier/project/...), these are the base prompts offered instead of the
// section's general starter pills, until the user exits or picks a different
// entity. Keyed by context.type (see CONTEXT_PARAM_KEYS server-side).
const CONTEXT_PROMPTS = {
	customer: (id) => [
		{ id: 'invoicing_customer_detail', label: 'Ver visão geral do cliente', params: { customer: id } },
		{ id: 'invoicing_customer_trend_comparison', label: 'Comparar com o mês passado', params: { customer: id } },
		{ id: 'invoicing_customer_all_invoices', label: 'Ver todo o histórico de faturas', params: { customer: id } },
	],
	project: (id) => [
		{ id: 'projects_detail', label: 'Ver visão geral do projeto', params: { project: id } },
		{ id: 'projects_trend_comparison', label: 'Comparar com o mês passado', params: { project: id } },
	],
};

class NextAI {
	constructor(page) {
		this.page = page;
		this.sections = [];
		this.activeSectionId = 'invoicing';
		this.trail = [];
		this.asked = new Set();
		this.context = null;
		this.searchTimer = null;
		this.searchSeq = 0;
		this.typeaheadItems = [];
		this.typeaheadIndex = -1;
		this.setup();
	}

	setup() {
		$(this.page.body).html(`
			<div class="next-ai">
				<div class="na-rail"></div>
				<div class="na-main">
					<div class="na-trail"></div>
					<div class="na-context-banner"></div>
					<div class="na-thread"></div>
					<div class="na-suggestions"></div>
					<div class="na-input-area">
						<div class="na-typeahead"></div>
						<form class="na-inputbar">
							<input type="text" class="na-input" placeholder="Escreva a sua pergunta..." autocomplete="off" />
							<button type="submit" class="na-send" aria-label="Enviar">↑</button>
						</form>
					</div>
				</div>
			</div>
		`);

		this.$wrapper = $(this.page.body).find('.next-ai');
		this.$rail = this.$wrapper.find('.na-rail');
		this.$trail = this.$wrapper.find('.na-trail');
		this.$contextBanner = this.$wrapper.find('.na-context-banner');
		this.$thread = this.$wrapper.find('.na-thread');
		this.$suggestions = this.$wrapper.find('.na-suggestions');
		this.$input = this.$wrapper.find('.na-input');
		this.$typeahead = this.$wrapper.find('.na-typeahead');

		this.$wrapper.find('.na-inputbar').on('submit', (e) => {
			e.preventDefault();
			this.handle_free_text();
		});

		this.$input.on('input', () => this.on_input_change());
		this.$input.on('keydown', (e) => this.on_input_keydown(e));
		this.$input.on('blur', () => setTimeout(() => this.hide_typeahead(), 150));

		this.page.add_inner_button(__('Reiniciar conversa'), () => this.restart());

		frappe.call('escopil_app.next_ai.page.next_ai.next_ai.get_sections').then((r) => {
			this.sections = r.message || [];
			this.render_rail();
			this.render_welcome();
			this.render_suggestions(this.current_section_prompts());
		});
	}

	current_section_prompts() {
		if (this.context && CONTEXT_PROMPTS[this.context.type]) {
			return CONTEXT_PROMPTS[this.context.type](this.context.id);
		}
		const section = this.sections.find((s) => s.id === this.activeSectionId);
		return section ? section.prompts : [];
	}

	render_context_banner() {
		if (!this.context) {
			this.$contextBanner.removeClass('is-visible').empty();
			return;
		}
		this.$contextBanner.html(`
			<span class="na-context-label">${frappe.utils.escape_html(this.context.label)}</span>
			<button type="button" class="na-context-exit">${frappe.utils.escape_html(__('Sair'))}</button>
		`).addClass('is-visible');
		this.$contextBanner.find('.na-context-exit').on('click', () => this.exit_context());
	}

	exit_context() {
		this.context = null;
		this.render_context_banner();
		this.render_suggestions(this.current_section_prompts());
	}

	render_rail() {
		this.$rail.empty();
		this.$rail.append(`<div class="na-brand">Next AI</div>`);

		SECTION_ORDER.forEach((id) => {
			const meta = SECTION_META[id];
			const active = id === this.activeSectionId ? 'is-active' : '';
			const disabled = meta.ready ? '' : 'is-disabled';
			const badge = meta.ready ? '' : '<span class="na-soon">Em breve</span>';
			const $btn = $(`
				<button type="button" class="na-section ${active} ${disabled}">
					<span>${frappe.utils.escape_html(meta.label)}</span>
					${badge}
				</button>
			`);
			if (meta.ready) {
				$btn.on('click', () => this.switch_section(id));
			}
			this.$rail.append($btn);
		});
	}

	switch_section(id) {
		if (id === this.activeSectionId) return;
		this.activeSectionId = id;
		this.restart();
	}

	restart() {
		this.trail = [];
		this.asked = new Set();
		this.context = null;
		this.render_context_banner();
		clearTimeout(this.searchTimer);
		this.hide_typeahead();
		this.$input.val('');
		this.$thread.empty();
		this.render_rail();
		this.render_welcome();
		this.render_suggestions(this.current_section_prompts());
	}

	render_welcome() {
		const label = SECTION_META[this.activeSectionId].label;
		this.$thread.empty();
		this.$trail.empty();
		this.append_bot_html(`
			<p>Olá! Sou o assistente <strong>Next AI</strong>.</p>
			<p>Escolha uma pergunta sobre <strong>${frappe.utils.escape_html(label)}</strong> para começar.</p>
		`);
	}

	render_trail() {
		if (!this.trail.length) {
			this.$trail.empty();
			return;
		}
		const crumbs = this.trail.map((t, idx) => {
			const isLast = idx === this.trail.length - 1;
			return `<span class="na-crumb ${isLast ? 'is-last' : ''}" data-idx="${idx}">${frappe.utils.escape_html(t)}</span>`;
		});
		this.$trail.html(crumbs.join('<span class="na-crumb-sep">›</span>'));
	}

	// --- asking flow -------------------------------------------------------

	prompt_key(id, params) {
		return id + '::' + JSON.stringify(params || {});
	}

	ask_prompt(prompt_id, label, params) {
		this.asked.add(this.prompt_key(prompt_id, params));
		this.append_user_bubble(label);
		this.trail.push(label);
		this.render_trail();
		this.render_suggestions([]);

		const $typing = this.append_typing_indicator();

		frappe.call({
			method: 'escopil_app.next_ai.page.next_ai.next_ai.ask',
			args: { prompt_id, params: params || {} },
			callback: (r) => {
				$typing.remove();
				const result = r.message || {};
				this.append_bot_result(result);
				if (result.context) {
					this.context = result.context;
					this.render_context_banner();
				}
				this.render_suggestions(result.follow_ups || []);
			},
			error: () => {
				$typing.remove();
				this.append_bot_html(`<p>Não consegui obter essa resposta agora. Tente novamente.</p>`);
				this.render_suggestions(this.current_section_prompts());
			},
		});
	}

	handle_free_text() {
		const raw = this.$input.val();
		const text = (raw || '').trim();
		if (!text) return;
		this.$input.val('');
		this.hide_typeahead();

		const match = this.match_prompt(text);
		if (match) {
			this.ask_prompt(match.id, match.label);
			return;
		}

		this.append_user_bubble(text);
		this.append_bot_html(`
			<p>Ainda não tenho uma resposta pronta para essa pergunta.</p>
			<p>Escolha uma das sugestões abaixo:</p>
		`);
		this.render_suggestions(this.current_section_prompts());
	}

	norm_text(s) {
		const ACCENTS = {
			'á': 'a', 'à': 'a', 'â': 'a', 'ã': 'a', 'ä': 'a',
			'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e',
			'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i',
			'ó': 'o', 'ò': 'o', 'ô': 'o', 'õ': 'o', 'ö': 'o',
			'ú': 'u', 'ù': 'u', 'û': 'u', 'ü': 'u',
			'ç': 'c',
		};
		return (s || '')
			.toLowerCase()
			.split('')
			.map((ch) => ACCENTS[ch] || ch)
			.join('')
			.replace(/[^a-z0-9 ]/g, '')
			.trim();
	}

	match_prompt(text) {
		const needle = this.norm_text(text);
		return this.current_section_prompts().find((p) => {
			const hay = this.norm_text(p.label);
			return hay === needle || hay.includes(needle) || needle.includes(hay);
		});
	}

	match_prompts(text, limit) {
		const needle = this.norm_text(text);
		if (!needle) return [];
		return this.current_section_prompts()
			.filter((p) => this.norm_text(p.label).includes(needle))
			.slice(0, limit || 5);
	}

	// --- typeahead -------------------------------------------------------

	on_input_change() {
		clearTimeout(this.searchTimer);
		const text = this.$input.val().trim();
		if (!text) {
			this.hide_typeahead();
			return;
		}
		this.searchTimer = setTimeout(() => this.run_typeahead(text), 220);
	}

	run_typeahead(text) {
		const seq = ++this.searchSeq;
		const promptMatches = this.match_prompts(text);

		frappe.call({
			method: 'escopil_app.next_ai.page.next_ai.next_ai.search_entities',
			args: { section_id: this.activeSectionId, query: text },
			callback: (r) => {
				if (seq !== this.searchSeq) return;
				this.render_typeahead(promptMatches, r.message || []);
			},
			error: () => {
				if (seq !== this.searchSeq) return;
				this.render_typeahead(promptMatches, []);
			},
		});
	}

	render_typeahead(promptMatches, entityMatches) {
		const items = [...promptMatches, ...entityMatches];
		this.typeaheadItems = items;
		this.typeaheadIndex = items.length ? 0 : -1;

		if (!items.length) {
			this.hide_typeahead();
			return;
		}

		const item_html = (item, idx) => `
			<div class="na-typeahead-item" data-idx="${idx}">
				<span>${frappe.utils.escape_html(item.display || item.label)}</span>
			</div>
		`;

		const entityLabel = SECTION_ENTITY_LABEL[this.activeSectionId] || __('Resultados');
		const promptHtml = promptMatches.map((p, idx) => item_html(p, idx)).join('');
		const entityHtml = entityMatches.length
			? `<div class="na-typeahead-caption">${frappe.utils.escape_html(entityLabel)}</div>`
				+ entityMatches.map((p, idx) => item_html(p, promptMatches.length + idx)).join('')
			: '';

		this.$typeahead.html(promptHtml + entityHtml).show();
		this.highlight_typeahead();

		this.$typeahead.find('.na-typeahead-item').on('click', (e) => {
			const idx = Number($(e.currentTarget).attr('data-idx'));
			this.select_typeahead(this.typeaheadItems[idx]);
		});
	}

	highlight_typeahead() {
		this.$typeahead.find('.na-typeahead-item').removeClass('is-active').eq(this.typeaheadIndex).addClass('is-active');
	}

	select_typeahead(item) {
		if (!item) return;
		this.$input.val('');
		this.hide_typeahead();
		this.ask_prompt(item.id, item.label, item.params);
	}

	hide_typeahead() {
		this.typeaheadItems = [];
		this.typeaheadIndex = -1;
		this.$typeahead.empty().hide();
	}

	on_input_keydown(e) {
		if (!this.typeaheadItems.length) return;

		if (e.key === 'ArrowDown') {
			e.preventDefault();
			this.typeaheadIndex = Math.min(this.typeaheadIndex + 1, this.typeaheadItems.length - 1);
			this.highlight_typeahead();
		} else if (e.key === 'ArrowUp') {
			e.preventDefault();
			this.typeaheadIndex = Math.max(this.typeaheadIndex - 1, 0);
			this.highlight_typeahead();
		} else if (e.key === 'Escape') {
			this.hide_typeahead();
		} else if (e.key === 'Enter' && this.typeaheadIndex >= 0) {
			e.preventDefault();
			this.select_typeahead(this.typeaheadItems[this.typeaheadIndex]);
		}
	}

	// --- rendering -----------------------------------------------------------

	append_user_bubble(label) {
		const $row = $(`
			<div class="na-row na-row-user">
				<div class="na-bubble na-bubble-user">${frappe.utils.escape_html(label)}</div>
			</div>
		`);
		this.$thread.append($row);
		this.scroll_to_bottom();
	}

	append_typing_indicator() {
		const $row = $(`
			<div class="na-row na-row-bot">
				<div class="na-avatar">N</div>
				<div class="na-bubble na-bubble-bot na-typing">
					<span></span><span></span><span></span>
				</div>
			</div>
		`);
		this.$thread.append($row);
		this.scroll_to_bottom();
		return $row;
	}

	append_bot_html(html, extraClass) {
		const $row = $(`
			<div class="na-row na-row-bot">
				<div class="na-avatar">N</div>
				<div class="na-bubble na-bubble-bot ${extraClass || ''}">${html}</div>
			</div>
		`);
		this.$thread.append($row);
		this.scroll_to_bottom();
		return $row;
	}

	append_bot_result(result) {
		const blocks = result.blocks || [];
		const isWide = blocks.some((b) => b.type === 'table' || b.type === 'comparison' || b.type === 'bar');

		const $row = $(`
			<div class="na-row na-row-bot">
				<div class="na-avatar">N</div>
				<div class="na-bubble na-bubble-bot ${isWide ? 'na-bubble-wide' : ''}"></div>
			</div>
		`);
		const $bubble = $row.find('.na-bubble');

		if (result.title) {
			$bubble.append(`<div class="na-answer-title">${frappe.utils.escape_html(result.title)}</div>`);
		}
		blocks.forEach((block) => $bubble.append(this.render_block(block)));

		this.$thread.append($row);
		this.scroll_to_bottom();
		return $row;
	}

	render_block(block) {
		if (block.type === 'metric') {
			return $(`
				<div class="na-metric">
					<div class="na-metric-label">${frappe.utils.escape_html(block.label)}</div>
					<div class="na-metric-value">${frappe.utils.escape_html(block.value)}</div>
				</div>
			`);
		}
		if (block.type === 'comparison') {
			return this.render_comparison_block(block);
		}
		if (block.type === 'table') {
			return this.render_table_block(block);
		}
		if (block.type === 'text') {
			return $(`<p class="na-text">${frappe.utils.escape_html(block.text)}</p>`);
		}
		if (block.type === 'kpi_grid') {
			const items = (block.items || []).map((it) => `
				<div class="na-kpi">
					<div class="na-metric-label">${frappe.utils.escape_html(it.label)}</div>
					<div class="na-metric-value na-metric-value-sm">${frappe.utils.escape_html(it.value)}</div>
				</div>
			`).join('');
			return $(`<div class="na-kpi-grid">${items}</div>`);
		}
		if (block.type === 'bar') {
			return $(this.render_bar_html(block));
		}
		if (block.type === 'trend') {
			return $(this.render_trend_html(block));
		}
		return $();
	}

	render_comparison_block(block) {
		const items = (block.items || []).map((it) => `
			<div class="na-compare-item">
				<div class="na-metric-label">${frappe.utils.escape_html(it.label)}</div>
				<div class="na-metric-value na-metric-value-sm">${frappe.utils.escape_html(it.value)}</div>
			</div>
		`).join('<div class="na-compare-arrow">→</div>');

		let delta = '';
		if (block.delta_pct !== null && block.delta_pct !== undefined) {
			const up = block.delta_pct >= 0;
			delta = `
				<div class="na-delta ${up ? 'is-up' : 'is-down'}">
					${up ? '▲' : '▼'} ${Math.abs(block.delta_pct).toFixed(1)}%
				</div>
			`;
		}
		return $(`<div class="na-compare-block"><div class="na-compare">${items}</div>${delta}</div>`);
	}

	render_table_block(block) {
		const head = (block.columns || []).map((c) => `<th>${frappe.utils.escape_html(c)}</th>`).join('');
		const rowsHtml = (block.rows || []).map((row, idx) => `
			<tr data-row-idx="${idx}">${row.map((cell) => `<td>${frappe.utils.escape_html(String(cell))}</td>`).join('')}</tr>
		`).join('');

		const $block = $(`
			<div class="na-table-block">
				<div class="na-table-wrap">
					<table class="na-table">
						<thead><tr>${head}</tr></thead>
						<tbody>${rowsHtml}</tbody>
					</table>
				</div>
			</div>
		`);

		if (block.link_column) {
			const { index, doctype, names } = block.link_column;
			$block.find('tbody tr').each((rowIdx, tr) => {
				const name = (names || [])[rowIdx];
				if (!name) return;
				const $cell = $(tr).find('td').eq(index);
				const href = this.doc_route(doctype, name);
				$cell.html(`<a href="${href}" target="_blank" rel="noopener" class="na-doc-link">${frappe.utils.escape_html($cell.text())}</a>`);
				$cell.find('a').on('click', (e) => e.stopPropagation());
			});
		}

		if (block.row_prompt_id) {
			const rowParams = block.row_params || [];
			const rowLabels = block.row_labels || [];
			$block.find('tbody tr')
				.addClass('na-row-clickable')
				.attr('title', __('Ver detalhe'))
				.on('click', (e) => {
					const idx = Number($(e.currentTarget).attr('data-row-idx'));
					this.ask_prompt(block.row_prompt_id, rowLabels[idx] || __('Ver detalhe'), rowParams[idx] || {});
				});
		}

		if (block.load_more) {
			const lm = block.load_more;
			const $more = $(`
				<button type="button" class="na-load-more">
					${frappe.utils.escape_html(lm.label)}
					<span class="na-load-more-hint">${__('faltam {0}', [lm.remaining])}</span>
				</button>
			`);
			$more.on('click', () => this.ask_prompt(lm.prompt_id, lm.label, lm.params));
			$block.append($more);
		}

		return $block;
	}

	doc_route(doctype, name) {
		const slug = (frappe.router && frappe.router.slug)
			? frappe.router.slug(doctype)
			: doctype.toLowerCase().replace(/ /g, '-');
		return `/app/${slug}/${encodeURIComponent(name)}`;
	}

	render_bar_html(block) {
		const items = block.items || [];
		if (!items.length) return '';
		const max = block.max || Math.max(...items.map((it) => Number(it.value) || 0), 1);

		const rows = items.map((it) => {
			const pct = Math.max(0, Math.min(100, ((Number(it.value) || 0) / max) * 100));
			return `
				<div class="na-bar-row">
					<div class="na-bar-label" title="${frappe.utils.escape_html(it.label)}">${frappe.utils.escape_html(it.label)}</div>
					<div class="na-bar-track">
						<div class="na-bar-fill" style="width:${pct}%"></div>
					</div>
					<div class="na-bar-value">${frappe.utils.escape_html(it.display || String(it.value))}</div>
				</div>
			`;
		}).join('');

		return `<div class="na-bar-chart">${rows}</div>`;
	}

	render_trend_html(block) {
		const series = (block.series && block.series.length)
			? block.series
			: ((block.points && block.points.length) ? [{ label: null, points: block.points }] : []);
		if (!series.length) return '';

		const primaryPoints = series[0].points || [];
		if (!primaryPoints.length) return '';

		const allValues = [];
		series.forEach((s) => (s.points || []).forEach((p) => allValues.push(Number(p.value) || 0)));
		const min = Math.min(...allValues, 0);
		const max = Math.max(...allValues, 1);
		const range = max - min || 1;
		const W = 300;
		const H = 70;
		const PAD = 6;
		const count = primaryPoints.length;
		const step = count > 1 ? (W - PAD * 2) / (count - 1) : 0;

		const toCoords = (points) => points.map((p, i) => {
			const x = PAD + step * i;
			const y = H - PAD - (((Number(p.value) || 0) - min) / range) * (H - PAD * 2);
			return [x, y];
		});

		const paths = series.map((s, idx) => {
			const coords = toCoords(s.points || []);
			const d = coords.map(([x, y], i) => `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
			const cls = idx === 0 ? 'na-trend-line' : 'na-trend-line na-trend-line-alt';
			const dots = idx === 0
				? coords.map(([x, y]) => `<circle cx="${x.toFixed(1)}" cy="${y.toFixed(1)}" r="2.5" class="na-trend-dot"></circle>`).join('')
				: '';
			return `<path d="${d}" class="${cls}" fill="none"></path>${dots}`;
		}).join('');

		const labels = primaryPoints.map((p) => `<span>${frappe.utils.escape_html(p.label)}</span>`).join('');
		const title = block.label ? `<div class="na-metric-label">${frappe.utils.escape_html(block.label)}</div>` : '';

		let legend = '';
		if (series.length > 1) {
			const items = series.map((s, idx) => `
				<span class="na-trend-legend-item ${idx === 0 ? '' : 'is-alt'}">${frappe.utils.escape_html(s.label || '')}</span>
			`).join('');
			legend = `<div class="na-trend-legend">${items}</div>`;
		}

		return `
			<div class="na-trend">
				${title}
				<svg viewBox="0 0 ${W} ${H}" class="na-trend-svg" preserveAspectRatio="none">
					${paths}
				</svg>
				<div class="na-trend-labels">${labels}</div>
				${legend}
			</div>
		`;
	}

	render_suggestions(prompts) {
		this.$suggestions.empty();

		const unseen = (prompts || []).filter((p) => !this.asked.has(this.prompt_key(p.id, p.params)));
		const fallback = unseen.length ? unseen : this.current_section_prompts().filter(
			(p) => !this.asked.has(this.prompt_key(p.id, p.params))
		);

		if (!fallback.length) {
			const $pill = $(`<button type="button" class="na-pill na-pill-restart">${__('Recomeçar')}</button>`);
			$pill.on('click', () => this.restart());
			this.$suggestions.append($pill);
			return;
		}

		fallback.forEach((p) => {
			const $pill = $(`<button type="button" class="na-pill">${frappe.utils.escape_html(p.label)}</button>`);
			$pill.on('click', () => this.ask_prompt(p.id, p.label, p.params));
			this.$suggestions.append($pill);
		});
	}

	scroll_to_bottom() {
		this.$thread.animate({ scrollTop: this.$thread.prop('scrollHeight') }, 150);
	}
}
