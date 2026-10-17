"""Smart mode: connect an AI and describe the ideal customer it scores leads against."""
from __future__ import annotations

from PyQt6.QtWidgets import QLineEdit, QSpinBox

from app.core import ai, credentials, db
from app.ui.pages.base import Page
from app.ui.widgets.common import (ChoiceButtons, FormRow, Section, danger_button, ghost_button,
                                   hint, muted, open_url, primary_button, row, secondary_button)
from app.ui.widgets.inputs import checkbox, combo, get_text, line_edit, password_edit, set_text, \
    text_box
from app.workers.base import Task

PROFILE_EXAMPLE = ("For example: independent dental clinics (not hospital chains) with a website "
                   "but little social media, rated under 4.5 stars, that might want help "
                   "getting more patients online.")


class SmartPage(Page):
    def __init__(self, window):
        super().__init__(window)
        self.add_header("Smart mode",
                        "Connect an AI and describe your ideal customer. While a search runs, the "
                        "AI checks every business is genuine and scores how well it fits, with a "
                        "one-line reason. You bring the AI, so GeoHarvest stays free.")
        body = self.scroll_body()
        layout = body.body_layout
        saved = db.get_setting("ai_provider", "")

        # --- 1. which AI ----------------------------------------------------
        choose = Section("1. Choose your AI",
                         "Free choices first. 'On this PC' runs entirely on your computer: free, "
                         "private, and fast if you have a strong graphics card.")
        self.provider = ChoiceButtons([(p.key, p.name) for p in ai.PROVIDERS],
                                      saved or "gemini", on_change=self._provider_changed)
        choose.add(self.provider)
        self.note = muted("")
        self.key_link = ghost_button("Get a key", lambda: open_url(self._current().key_url))
        choose.add(row(self.note, self.key_link, stretch=0))

        self.key_row = FormRow("Key", "Stored encrypted on this computer, readable only by your "
                                      "Windows account. Sent only to the provider you picked.")
        self.key = password_edit("Paste your key here")
        self.show_key = secondary_button("Show", self._toggle_key)
        self.key_row.add(row(self.key, self.show_key, stretch=0))
        choose.add(self.key_row)

        self.url_row = FormRow("Address", "Where the AI service is listening.")
        self.base_url = line_edit("http://localhost:11434/v1")
        self.url_row.add(self.base_url)
        choose.add(self.url_row)

        model_row = FormRow("Model", "Press 'Load models' to see what your key can use.")
        self.model = combo([], translate=False)
        self.model.setEditable(True)
        self.model.setMinimumWidth(380)
        self.load_button = secondary_button("Load models", self.load_models)
        model_row.add(row(self.model, self.load_button, None))
        choose.add(model_row)
        layout.addWidget(choose)

        # --- 2. ideal customer ----------------------------------------------
        profile = Section("2. Describe your ideal customer",
                          "Plain words are fine. The more specific you are, the better the scores. "
                          "What you are selling, who buys it, and who is not worth contacting.")
        self.profile = text_box(PROFILE_EXAMPLE, lines=5)
        set_text(self.profile, db.get_setting("ai_profile", ""))
        profile.add(self.profile)
        layout.addWidget(profile)

        # --- 3. low scores --------------------------------------------------
        low = Section("3. Leads that do not fit")
        min_score = int(db.get_setting("ai_min_score", 0) or 0)
        self.drop_low = checkbox("Leave out leads the AI scores below", bool(min_score))
        self.min_score = QSpinBox()
        self.min_score.setRange(1, 100)
        self.min_score.setValue(min_score or 50)
        self.min_score.setFixedWidth(90)
        low.add(row(self.drop_low, self.min_score, None))
        low.add(hint("Scores: 80 and up is a good fit, 50 to 79 maybe, below 50 a poor fit. "
                     "Leave this off to keep every lead and sort by AI score on the Leads page."))
        layout.addWidget(low)
        layout.addStretch(1)

        self.status = muted("", wrap=True)
        self.root.addWidget(self.status)
        self.save_button = primary_button("Save and test", self.save_and_test)
        self.off_button = danger_button("Turn Smart mode off", self.turn_off)
        self.root.addWidget(row(None, self.off_button, self.save_button))

        self._provider_changed(self.provider.get())
        self._show_state()

    # --- form ---------------------------------------------------------------
    def _current(self) -> ai.Provider:
        return ai.BY_KEY[self.provider.get()]

    def _provider_changed(self, key: str) -> None:
        provider = ai.BY_KEY[key]
        self.note.setText(provider.note)
        self.key_link.setVisible(bool(provider.key_url))
        self.key_link.setText("Get a free key" if "Free" in provider.note and provider.needs_key
                              else "Get a key" if provider.needs_key else "Download")
        self.key_row.setVisible(provider.kind != "openai" or provider.needs_key
                                or key == "custom")
        self.key.setText(credentials.load_secret(credentials.ai_key_name(key)))
        local = not provider.needs_key
        self.url_row.setVisible(local)
        same = key == db.get_setting("ai_provider", "")
        self.base_url.setText((db.get_setting("ai_base_url", "") if same else "")
                              or provider.base_url)
        self.model.clear()
        self.model.lineEdit().setText((db.get_setting("ai_model", "") if same else "")
                                      or provider.model)

    def _toggle_key(self) -> None:
        hidden = self.key.echoMode() == QLineEdit.EchoMode.Password
        self.key.setEchoMode(QLineEdit.EchoMode.Normal if hidden else QLineEdit.EchoMode.Password)
        self.show_key.setText("Hide" if hidden else "Show")

    def _form_config(self) -> dict:
        provider = self._current()
        return {
            "provider": provider.key, "kind": provider.kind,
            "base_url": (self.base_url.text().strip() if self.url_row.isVisible()
                         else provider.base_url).rstrip("/"),
            "model": self.model.lineEdit().text().strip(),
            "key": self.key.text().strip(),
            "profile": get_text(self.profile),
            "min_score": self.min_score.value() if self.drop_low.isChecked() else 0,
        }

    def _show_state(self) -> None:
        cfg = ai.settings()
        self.off_button.setEnabled(cfg is not None)
        if cfg is None:
            self.status.setText("Smart mode is off. Set it up above, then press Save and test.")
        else:
            self.status.setText(f"Smart mode is on: {ai.BY_KEY[cfg['provider']].name}, "
                                f"model {cfg['model']}. Switch on 'Smart mode' on the New search page "
                                "to use it.")

    # --- actions ------------------------------------------------------------
    def load_models(self) -> None:
        cfg = self._form_config()
        self.load_button.setEnabled(False)
        self.load_button.setText("Loading...")

        def done(models: list) -> None:
            typed = self.model.lineEdit().text()
            self.model.clear()
            self.model.addItems(models)
            self.model.lineEdit().setText(typed if typed in models or not models else models[0])
            self.notify(f"{len(models)} models available." if models else
                        "No models found. Is a model downloaded and loaded?",
                        "success" if models else "warn")

        def finish() -> None:
            self.load_button.setEnabled(True)
            self.load_button.setText("Load models")

        Task(ai.list_models, cfg).start(on_result=self.guard(done),
                                        on_error=self.guard(lambda m: self.notify(m, "error", 8000)),
                                        on_done=self.guard(finish))

    def save(self) -> dict:
        cfg = self._form_config()
        credentials.save_secret(credentials.ai_key_name(cfg["provider"]), cfg["key"])
        db.set_setting("ai_provider", cfg["provider"])
        db.set_setting("ai_model", cfg["model"])
        db.set_setting("ai_base_url", cfg["base_url"] if self.url_row.isVisible() else "")
        db.set_setting("ai_profile", cfg["profile"])
        db.set_setting("ai_min_score", cfg["min_score"])
        self._show_state()
        self.window_.refresh_status()
        return cfg

    def save_and_test(self) -> None:
        cfg = self.save()
        self.save_button.setEnabled(False)
        self.status.setText("Testing: asking the AI to score a sample business...")

        def done(result: dict) -> None:
            self.status.setText(f"Working. The AI scored a sample dental clinic "
                                f"{result['ai_score']} ({result['ai_verdict']}): "
                                f"{result['ai_reason']}")
            self.notify("Smart mode is working.", "success")

        def failed(message: str) -> None:
            self.status.setText(f"Saved, but the test failed: {message}")
            self.notify(message, "error", 8000)

        Task(ai.test, cfg).start(on_result=self.guard(done), on_error=self.guard(failed),
                                 on_done=self.guard(lambda: self.save_button.setEnabled(True)))

    def turn_off(self) -> None:
        db.set_setting("ai_provider", "")
        self._show_state()
        self.window_.refresh_status()
        self.notify("Smart mode is off. Your key stays saved in case you turn it back on.")
