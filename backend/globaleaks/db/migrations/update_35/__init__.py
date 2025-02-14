# -*- coding: utf-8
from globaleaks import models
from globaleaks.db.migrations.update import MigrationBase
from globaleaks.models.properties import *
from globaleaks.utils.utility import datetime_now, datetime_null


class WhistleblowerTip_v_34(models.Model):
    __tablename__ = 'whistleblowertip'
    id = Column(UnicodeText(36), primary_key=True, default=uuid4, nullable=False)
    internaltip_id = Column(UnicodeText(36))
    receipt_hash = Column(UnicodeText)


class InternalTip_v_34(models.Model):
    __tablename__ = 'internaltip'
    id = Column(UnicodeText(36), primary_key=True, default=uuid4, nullable=False)
    creation_date = Column(DateTime, default=datetime_now)
    update_date = Column(DateTime, default=datetime_now)
    context_id = Column(UnicodeText(36))
    questionnaire_hash = Column(UnicodeText)
    progressive = Column(Integer, default=0)
    tor2web = Column(Boolean, default=False)
    total_score = Column(Integer, default=0)
    expiration_date = Column(DateTime)
    identity_provided = Column(Boolean, default=False)
    identity_provided_date = Column(DateTime, default=datetime_null)
    enable_two_way_comments = Column(Boolean, default=True)
    enable_two_way_messages = Column(Boolean, default=True)
    enable_attachments = Column(Boolean, default=True)
    enable_whistleblower_identity = Column(Boolean, default=False)
    wb_last_access = Column(DateTime, default=datetime_now)


class MigrationScript(MigrationBase):
    def migrate_User(self):
        default_language = self.session_new.query(self.model_to['Config']).filter(self.model_to['Config'].var_name == 'default_language').one().value['v']
        enabled_languages = [r[0] for r in self.session_old.query(self.model_to['EnabledLanguage'].name)]

        for old_obj in self.session_old.query(self.model_from['User']):
            new_obj = self.model_to['User']()
            for key in new_obj.__table__.columns._data.keys():
                if key in ['pgp_key_public', 'pgp_key_fingerprint', 'pgp_key_expiration'] and getattr(old_obj, key) is None:
                    pass

                elif key == 'language' and getattr(old_obj, key) not in enabled_languages:
                    # fix users that have configured a language that has never been there
                    setattr(new_obj, key, default_language)

                else:
                    setattr(new_obj, key, getattr(old_obj, key))

            self.session_new.add(new_obj)

    def migrate_WhistleblowerTip(self):
        for old_obj in self.session_old.query(self.model_from['WhistleblowerTip']):
            new_obj = self.model_to['WhistleblowerTip']()
            for key in new_obj.__table__.columns._data.keys():
                if key == 'id':
                    new_obj.id = old_obj.internaltip_id
                else:
                    setattr(new_obj, key, getattr(old_obj, key))

            self.session_new.add(new_obj)
