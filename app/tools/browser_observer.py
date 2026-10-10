"""Browser Observer - Stage 18: Computer Use Foundation.

Responsible for observing and extracting browser state (DOM, accessibility tree, elements, etc.).
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from app.tools.browser_state import (
    BrowserElement,
    BrowserForm,
    BrowserSession,
    BrowserTab,
    ElementType,
    TabStatus,
    create_browser_session,
    get_browser_session,
)


class BrowserObserver:
    """Observes browser state and extracts structured information."""

    def __init__(self, session: BrowserSession):
        self.session = session
        self._playwright_page = None  # Will be set externally

    def set_page(self, page):
        """Set the Playwright page to observe."""
        self._playwright_page = page

    async def observe_active_tab(self) -> BrowserTab:
        """Observe and update the active tab's state."""
        tab = self.session.get_active_tab()
        if not tab:
            raise ValueError("No active tab")
        return await self.observe_tab(tab.tab_id)

    async def observe_tab(self, tab_id: str) -> BrowserTab:
        """Observe and update a specific tab's state."""
        tab = self.session.get_tab(tab_id)
        if not tab:
            raise ValueError(f"Tab {tab_id} not found")

        if not self._playwright_page:
            raise RuntimeError("Playwright page not set")

        try:
            # Update basic info
            tab.url = self._playwright_page.url
            tab.title = await self._playwright_page.title()
            tab.status = TabStatus.READY
            tab.last_accessed = time.time()

            # Extract perception data
            await self._extract_accessibility_tree(tab)
            await self._extract_visible_text(tab)
            await self._extract_interactive_elements(tab)
            await self._extract_forms(tab)
            await self._extract_page_metadata(tab)

            return tab
        except Exception:
            tab.status = TabStatus.ERROR
            raise

    async def _extract_accessibility_tree(self, tab: BrowserTab) -> None:
        """Extract accessibility tree using Playwright's accessibility snapshot."""
        try:
            # Get accessibility snapshot
            snapshot = await self._playwright_page.accessibility.snapshot()
            if snapshot:
                tab.accessibility_tree = json.dumps(snapshot, indent=2)
        except Exception:
            # Fallback: try to get simplified tree
            try:
                tree = await self._playwright_page.evaluate("""
                    () => {
                        function getTree(node, depth = 0) {
                            if (!node || depth > 10) return null;
                            const result = {
                                role: node.role,
                                name: node.name,
                                description: node.description,
                                value: node.value,
                                children: []
                            };
                            if (node.children) {
                                for (const child of node.children) {
                                    const childTree = getTree(child, depth + 1);
                                    if (childTree) result.children.push(childTree);
                                }
                            }
                            return result;
                        }
                        return getTree(document.documentElement);
                    }
                """)
                if tree:
                    tab.accessibility_tree = json.dumps(tree, indent=2)
            except Exception:
                tab.accessibility_tree = "{}"

    async def _extract_visible_text(self, tab: BrowserTab) -> None:
        """Extract visible text content from the page."""
        try:
            text = await self._playwright_page.evaluate("""
                () => {
                    // Get all visible text, excluding scripts/styles
                    const walker = document.createTreeWalker(
                        document.body,
                        NodeFilter.SHOW_TEXT,
                        {
                            acceptNode: function(node) {
                                const parent = node.parentElement;
                                if (!parent) return NodeFilter.FILTER_REJECT;
                                const style = window.getComputedStyle(parent);
                                if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                                    return NodeFilter.FILTER_REJECT;
                                }
                                if (parent.tagName === 'SCRIPT' || parent.tagName === 'STYLE') {
                                    return NodeFilter.FILTER_REJECT;
                                }
                                return NodeFilter.FILTER_ACCEPT;
                            }
                        }
                    );
                    
                    let text = '';
                    let node;
                    while (node = walker.nextNode()) {
                        const t = node.textContent.trim();
                        if (t) text += t + '\\n';
                    }
                    return text.slice(0, 50000); // Limit size
                }
            """)
            tab.visible_text = text
        except Exception:
            tab.visible_text = ""

    async def _extract_interactive_elements(self, tab: BrowserTab) -> None:
        """Extract all interactive elements from the page."""
        try:
            elements = await self._playwright_page.evaluate("""
                () => {
                    const elements = [];
                    const selector = 'button, a[href], input, textarea, select, [role="button"], [role="link"], [role="checkbox"], [role="radio"], [role="menuitem"], [role="tab"], [role="option"], [onclick], [tabindex]';
                    const nodes = document.querySelectorAll(selector);
                    
                    for (let i = 0; i < nodes.length; i++) {
                        const el = nodes[i];
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        
                        // Skip hidden elements
                        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                            continue;
                        }
                        if (rect.width === 0 && rect.height === 0) {
                            continue;
                        }
                        
                        const tag = el.tagName.toLowerCase();
                        const role = el.getAttribute('role');
                        const type = el.getAttribute('type');
                        
                        // Determine element type
                        let elementType = 'generic';
                        if (tag === 'button' || role === 'button' || (tag === 'input' && type === 'button')) {
                            elementType = 'button';
                        } else if (tag === 'a' && el.hasAttribute('href')) {
                            elementType = 'link';
                        } else if (tag === 'input') {
                            if (['text', 'email', 'password', 'search', 'url', 'tel', 'number'].includes(type)) {
                                elementType = 'input';
                            } else if (type === 'checkbox') {
                                elementType = 'checkbox';
                            } else if (type === 'radio') {
                                elementType = 'radio';
                            } else if (type === 'submit' || type === 'button') {
                                elementType = 'button';
                            } else {
                                elementType = 'input';
                            }
                        } else if (tag === 'textarea') {
                            elementType = 'textarea';
                        } else if (tag === 'select') {
                            elementType = 'select';
                        } else if (role === 'link') {
                            elementType = 'link';
                        } else if (role === 'checkbox') {
                            elementType = 'checkbox';
                        } else if (role === 'radio') {
                            elementType = 'radio';
                        }
                        
                        // Get accessible name
                        let label = el.getAttribute('aria-label') || 
                                   el.getAttribute('aria-labelledby') ||
                                   el.getAttribute('title') ||
                                   el.getAttribute('placeholder') ||
                                   (el.labels && el.labels[0] ? el.labels[0].textContent : null) ||
                                   el.textContent?.trim().slice(0, 100);
                        
                        elements.push({
                            element_id: `el_${i}`,
                            element_type: elementType,
                            role: role,
                            label: label,
                            placeholder: el.getAttribute('placeholder'),
                            text: el.textContent?.trim().slice(0, 200),
                            value: el.value,
                            href: el.getAttribute('href'),
                            selector: getSelector(el),
                            bounding_box: {
                                x: rect.x,
                                y: rect.y,
                                width: rect.width,
                                height: rect.height
                            },
                            is_visible: style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0',
                            is_enabled: !el.disabled && !el.hasAttribute('aria-disabled'),
                            is_editable: tag === 'input' || tag === 'textarea' || el.isContentEditable,
                            attributes: getAttributes(el)
                        });
                    }
                    return elements;
                    
                    function getSelector(el) {
                        if (el.id) return `#${el.id}`;
                        let path = [];
                        while (el && el !== document.body) {
                            let selector = el.tagName.toLowerCase();
                            if (el.className) {
                                const classes = el.className.split(' ').filter(c => c);
                                if (classes.length) selector += '.' + classes.join('.');
                            }
                            path.unshift(selector);
                            el = el.parentElement;
                        }
                        return path.join(' > ');
                    }
                    
                    function getAttributes(el) {
                        const attrs = {};
                        for (const attr of el.attributes) {
                            if (!attr.name.startsWith('on') && attr.name !== 'style') {
                                attrs[attr.name] = attr.value;
                            }
                        }
                        return attrs;
                    }
                }
            """)

            tab.interactive_elements = [
                BrowserElement.from_dict(el_data) for el_data in elements
            ]
        except Exception:
            tab.interactive_elements = []

    async def _extract_forms(self, tab: BrowserTab) -> None:
        """Extract forms from the page."""
        try:
            forms = await self._playwright_page.evaluate("""
                () => {
                    const forms = [];
                    for (const form of document.forms) {
                        const fields = [];
                        for (const field of form.elements) {
                            if (['input', 'textarea', 'select'].includes(field.tagName.toLowerCase())) {
                                fields.push({
                                    name: field.name,
                                    type: field.type,
                                    value: field.value,
                                    required: field.required,
                                    placeholder: field.placeholder
                                });
                            }
                        }
                        const submitBtn = form.querySelector('button[type="submit"], input[type="submit"]');
                        forms.push({
                            form_id: form.id || form.name || `form_${forms.length}`,
                            action: form.action,
                            method: form.method,
                            fields: fields,
                            submit_button: submitBtn ? {
                                text: submitBtn.textContent?.trim(),
                                value: submitBtn.value
                            } : null
                        });
                    }
                    return forms;
                }
            """)

            tab.forms = []
            for form_data in forms:
                form = BrowserForm(
                    form_id=form_data["form_id"],
                    action=form_data["action"],
                    method=form_data["method"],
                    fields=[
                        BrowserElement(
                            element_id=f"field_{f['name']}",
                            element_type=ElementType.INPUT,
                            label=f['name'],
                            placeholder=f['placeholder'],
                            value=f['value'],
                            attributes={'required': str(f['required'])}
                        )
                        for f in form_data["fields"]
                    ],
                    submit_button=BrowserElement(
                        element_id="submit",
                        element_type=ElementType.BUTTON,
                        label=form_data["submit_button"]["text"] if form_data["submit_button"] else "Submit",
                        text=form_data["submit_button"]["text"] if form_data["submit_button"] else "Submit"
                    ) if form_data["submit_button"] else None
                )
                tab.forms.append(form)
        except Exception:
            tab.forms = []

    async def _extract_page_metadata(self, tab: BrowserTab) -> None:
        """Extract page metadata."""
        try:
            metadata = await self._playwright_page.evaluate("""
                () => {
                    const meta = {};
                    for (const m of document.querySelectorAll('meta')) {
                        if (m.getAttribute('name')) {
                            meta[m.getAttribute('name')] = m.getAttribute('content');
                        }
                        if (m.getAttribute('property')) {
                            meta[m.getAttribute('property')] = m.getAttribute('content');
                        }
                    }
                    return {
                        meta: meta,
                        canonical: document.querySelector('link[rel="canonical"]')?.href,
                        language: document.documentElement.lang,
                        charset: document.characterSet,
                        viewport: document.querySelector('meta[name="viewport"]')?.getAttribute('content'),
                        has_iframes: document.querySelectorAll('iframe').length > 0,
                        iframe_count: document.querySelectorAll('iframe').length,
                    };
                }
            """)
            tab.page_metadata = metadata
        except Exception:
            tab.page_metadata = {}

    async def take_screenshot(self, tab_id: str, path: str | None = None) -> str:
        """Take a screenshot of the tab."""
        tab = self.session.get_tab(tab_id)
        if not tab:
            raise ValueError(f"Tab {tab_id} not found")

        if not self._playwright_page:
            raise RuntimeError("Playwright page not set")

        if path is None:
            path = f"screenshots/session_{self.session.session_id}_tab_{tab_id}_{int(time.time())}.png"

        Path(path).parent.mkdir(parents=True, exist_ok=True)

        await self._playwright_page.screenshot(path=path, full_page=True)
        tab.screenshot_path = path
        return path

    async def observe_all_tabs(self) -> dict[str, BrowserTab]:
        """Observe all tabs in the session."""
        results = {}
        for tab_id in list(self.session.tabs.keys()):
            try:
                results[tab_id] = await self.observe_tab(tab_id)
            except Exception:
                results[tab_id] = self.session.get_tab(tab_id)
        return results


def create_observer(session_id: str | None = None) -> BrowserObserver:
    """Create a browser observer for a session."""
    if session_id:
        session = get_browser_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")
    else:
        session = create_browser_session()
    return BrowserObserver(session)
