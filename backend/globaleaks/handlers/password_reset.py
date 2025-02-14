# -*- coding: utf-8 -*-
import os
from datetime import datetime, timedelta

from nacl.encoding import Base32Encoder, Base64Encoder

from sqlalchemy import or_

from globaleaks import models
from globaleaks.handlers.admin.notification import db_get_notification
from globaleaks.handlers.admin.node import db_admin_serialize_node
from globaleaks.handlers.base import BaseHandler
from globaleaks.handlers.user import user_serialize_user
from globaleaks.orm import db_log, transact
from globaleaks.rest import requests
from globaleaks.sessions import Sessions
from globaleaks.state import State
from globaleaks.utils.crypto import generateRandomKey, totpVerify, GCE
from globaleaks.utils.utility import datetime_now, datetime_null


def db_generate_password_reset_token(session, user):
    """
    Transaction for issuing password reset tokens

    :param session: An ORM session
    :param user: The user for which issuing a password reset token
    """
    token = generateRandomKey()

    if user.last_login > datetime_null():
        template = 'password_reset_validation'
    else:
        template = 'account_activation'

    user_desc = user_serialize_user(session, user, user.language)

    try:
        with open(os.path.abspath(os.path.join(State.settings.ramdisk_path, token)), "wb") as f:
            f.write(user.id.encode())
    except:
        pass

    template_vars = {
        'type': template,
        'user': user_desc,
        'reset_token': token,
        'node': db_admin_serialize_node(session, user.tid, user.language),
        'notification': db_get_notification(session, user.tid, user.language)
    }

    State.format_and_send_mail(session, user.tid, user_desc['mail_address'], template_vars)

    return token


@transact
def generate_password_reset_token_by_user_id(session, tid, user_id):
    """
    Transaction for generating a password reset token for a user identified by a user ID

    :param session: An ORM session
    :param tid: The tenant on
    :param user_id: The user id of the user for which issue a password reset
    :return:
    """
    user = session.query(models.User).filter(models.User.tid == tid, models.User.id == user_id).one_or_none()
    if user is not None:
        db_generate_password_reset_token(session, user)

    return {'redirect': '/login/passwordreset/requested'}


@transact
def generate_password_reset_token_by_username_or_mail(session, tid, username_or_email):
    """
    Transaction for generating a password reset token for a user identified by a username or email

    :param session: An ORM session
    :param tid: The tenant ID
    :param username_or_email: The username or the email of an user
    :return: A descriptor of the result
    """
    users = session.query(models.User).filter(
      or_(models.User.username == username_or_email,
          models.User.mail_address == username_or_email),
      models.User.tid == tid
    ).distinct()

    for user in users:
        db_generate_password_reset_token(session, user)

    return {'redirect': '/login/passwordreset/requested'}


@transact
def validate_password_reset(session, reset_token, auth_code, recovery_key):
    """
    Retrieves a user given a password reset validation token

    :param session: An ORM session
    :param reset_token: A reset token
    :param auth_code: A two factor authentication code (optional)
    :param recovery_key: An encryption recovery key (optional)
    :return: A descriptor describing the result of the operation
    """
    user_id = None
    now = datetime.now()
    prv_key = ''

    try:
        with open(os.path.abspath(os.path.join(State.settings.ramdisk_path, reset_token)), "r") as f:
            token = f.read()
            user_id = token.split(":")[0]
    except:
        return {'status': 'invalid_reset_token_provided'}

    user = session.query(models.User).filter(models.User.id == user_id).one_or_none()
    if user is None:
        return {'status': 'invalid_reset_token_provided'}

    # If encryption is enabled require the recovery key
    if user.crypto_prv_key:
        try:
            try:
                prv_key = token.split(":")[1]
            except:
                pass

            if prv_key:
                enc_key = GCE.derive_key(reset_token, user.salt)
                prv_key = GCE.symmetric_decrypt(enc_key, Base64Encoder.decode(prv_key))
            else:
                recovery_key = recovery_key.replace('-', '').upper() + '===='
                recovery_key = Base32Encoder.decode(recovery_key.encode())
                prv_key = GCE.symmetric_decrypt(recovery_key, Base64Encoder.decode(user.crypto_bkp_key))
        except:
            return {'status': 'require_recovery_key'}

    elif user.two_factor_secret:
        try:
            totpVerify(user.two_factor_secret, auth_code)
        except:
            return {'status': 'require_two_factor_authentication'}

    # Require password change
    user.password_change_needed = True

    user.last_login = datetime_now()

    user_session = Sessions.new(user.tid, user.id,
                           user.tid, user.role,
                           prv_key,
                           user.crypto_escrow_prv_key)

    user_session.properties['reset_token'] = reset_token

    db_log(session, tid=user.tid, type='login', user_id=user.id)

    return {'status': 'success', 'token': user_session.id}


class PasswordResetHandler(BaseHandler):
    """Handler that implements password reset API"""
    check_roles = 'any'

    def post(self):
        request = self.validate_message(self.request.content.read(),
                                        requests.PasswordReset1Desc)

        return generate_password_reset_token_by_username_or_mail(self.request.tid,
                                                                 request['username'])

    def put(self):
        request = self.validate_message(self.request.content.read(),
                                        requests.PasswordReset2Desc)

        return validate_password_reset(request['reset_token'],
                                       request['auth_code'],
                                       request['recovery_key'])
