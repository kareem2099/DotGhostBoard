"""Authenticated Vault key envelopes; independent passwords never use a Dashboard key."""

import base64
import hmac
import json
import os
from core import crypto
from core.security.passwords import derive_password_key, new_kdf_config, validate_new_password

CONFIG_KEY = 'credential_config'


class VaultCredentials:
    def __init__(self, repository):
        self.repo = repository

    def config(self):
        raw = self.repo.get_metadata(CONFIG_KEY)
        if raw is None:
            return None
        config = json.loads(raw)
        if not isinstance(config, dict) or config.get('version') != 2 or config.get('mode') not in ('shared', 'independent'):
            raise ValueError('Unsupported Vault credential format.')
        if config['mode'] == 'independent' and not isinstance(config.get('kdf'), dict):
            raise ValueError('Invalid Vault password KDF configuration.')
        return config

    @property
    def independent(self):
        config = self.config()
        return bool(config and config['mode'] == 'independent')

    @staticmethod
    def aad(config):
        if config is None:
            return None  # Legacy envelope; rewritten after successful authentication.
        return b'dotghostboard:vault:envelope:v2:' + json.dumps(config, sort_keys=True, separators=(',', ':')).encode()

    def unwrap(self, kek):
        config = self.config()
        wrapped = self.repo.get_metadata('wrapped_dek')
        if wrapped is None:
            if self.repo.count_items() or config is not None:
                raise RuntimeError('Vault contains encrypted items but wrapped DEK is missing.')
            dek = os.urandom(32)
            self.write(dek, kek, {'version': 2, 'mode': 'shared'})
            return dek
        dek = base64.urlsafe_b64decode(crypto.decrypt(wrapped, kek, self.aad(config)).encode('ascii'))
        if len(dek) != 32:
            raise ValueError('Vault data key must contain exactly 32 bytes.')
        if config is None:
            self.write(dek, kek, {'version': 2, 'mode': 'shared'})
        return dek

    def write(self, dek, kek, config):
        wrapped = crypto.encrypt(base64.urlsafe_b64encode(dek).decode('ascii'), kek, self.aad(config))
        self.repo.set_metadata_many({
            'wrapped_dek': wrapped, CONFIG_KEY: json.dumps(config, sort_keys=True),
        })

    def key_for_password(self, password):
        config = self.config()
        return (derive_password_key(password, config['kdf']) if self.independent
                else crypto.derive_vault_key(password))

    def configure(self, dashboard_password, new_password=None, current_password=None):
        if not crypto.verify_password(dashboard_password):
            raise ValueError('Incorrect Dashboard password.')
        if new_password is not None:
            validate_new_password(new_password)
            if hmac.compare_digest(new_password.encode(), dashboard_password.encode()):
                raise ValueError('The independent Vault password must differ from the Dashboard password.')
        if self.independent:
            if current_password is None:
                raise ValueError('Enter the current Vault password.')
            old_kek = self.key_for_password(current_password)
        else:
            old_kek = crypto.derive_vault_key(dashboard_password)
        dek = self.unwrap(old_kek)
        if new_password is not None:
            config = {'version': 2, 'mode': 'independent', 'kdf': new_kdf_config()}
            kek = derive_password_key(new_password, config['kdf'])
        else:
            config = {'version': 2, 'mode': 'shared'}
            kek = crypto.derive_vault_key(dashboard_password)
        self.write(dek, kek, config)
