"""
Unit tests for django-registration.

"""

import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase

from registration import forms
from registration.models import RegistrationProfile


class RegistrationFormsTestCase(TestCase):
    """
    Test the default registration forms.
    
    """
    def test_registration_form(self):
        """
        Test that ``RegistrationForm`` enforces username constraints
        and matching passwords.
        
        """
        # Create a user so we can verify that duplicate usernames aren't
        # permitted.
        User.objects.create_user('alice', 'alice@example.com', 'secret')

        invalid_data_dicts = [
            # Non-alphanumeric username.
            {
            'data':
            { 'username': 'foo/bar',
              'email': 'foo@example.com',
              'password1': 'foo',
              'password2': 'foo' },
            'error':
            ('username', [u"This value must contain only letters, numbers and underscores."])
            },
            # Already-existing username.
            {
            'data':
            { 'username': 'alice',
              'email': 'alice@example.com',
              'password1': 'secret',
              'password2': 'secret' },
            'error':
            ('username', [u"This username is already taken. Please choose another."])
            },
            # Mismatched passwords.
            {
            'data':
            { 'username': 'foo',
              'email': 'foo@example.com',
              'password1': 'foo',
              'password2': 'bar' },
            'error':
            ('__all__', [u"You must type the same password each time"])
            },
            ]

        for invalid_dict in invalid_data_dicts:
            form = forms.RegistrationForm(data=invalid_dict['data'])
            self.failIf(form.is_valid())
            self.assertEqual(form.errors[invalid_dict['error'][0]], invalid_dict['error'][1])

        form = forms.RegistrationForm(data={ 'username': 'foo',
                                             'email': 'foo@example.com',
                                             'password1': 'foo',
                                             'password2': 'foo' })
        self.failUnless(form.is_valid())

    def test_registration_form_tos(self):
        """
        Test that ``RegistrationFormTermsOfService`` requires
        agreement to the terms of service.
        
        """
        form = forms.RegistrationFormTermsOfService(data={ 'username': 'foo',
                                                           'email': 'foo@example.com',
                                                           'password1': 'foo',
                                                           'password2': 'foo' })
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['tos'], [u"You must agree to the terms to register"])
        
        form = forms.RegistrationFormTermsOfService(data={ 'username': 'foo',
                                                           'email': 'foo@example.com',
                                                           'password1': 'foo',
                                                           'password2': 'foo',
                                                           'tos': 'on' })
        self.failUnless(form.is_valid())

    def test_registration_form_unique_email(self):
        """
        Test that ``RegistrationFormUniqueEmail`` validates uniqueness
        of email addresses.
        
        """
        # Create a user so we can verify that duplicate addresses
        # aren't permitted.
        User.objects.create_user('alice', 'alice@example.com', 'secret')
        
        form = forms.RegistrationFormUniqueEmail(data={ 'username': 'foo',
                                                        'email': 'alice@example.com',
                                                        'password1': 'foo',
                                                        'password2': 'foo' })
        self.failIf(form.is_valid())
        self.assertEqual(form.errors['email'], [u"This email address is already in use. Please supply a different email address."])

        form = forms.RegistrationFormUniqueEmail(data={ 'username': 'foo',
                                                        'email': 'foo@example.com',
                                                        'password1': 'foo',
                                                        'password2': 'foo' })
        self.failUnless(form.is_valid())

    def test_registration_form_no_free_email(self):
        """
        Test that ``RegistrationFormNoFreeEmail`` disallows
        registration with free email addresses.
        
        """
        base_data = { 'username': 'foo',
                      'password1': 'foo',
                      'password2': 'foo' }
        for domain in ('aim.com', 'aol.com', 'email.com', 'gmail.com',
                       'googlemail.com', 'hotmail.com', 'hushmail.com',
                       'msn.com', 'mail.ru', 'mailinator.com', 'live.com'):
            invalid_data = base_data.copy()
            invalid_data['email'] = u"foo@%s" % domain
            form = forms.RegistrationFormNoFreeEmail(data=invalid_data)
            self.failIf(form.is_valid())
            self.assertEqual(form.errors['email'], [u"Registration using free email addresses is prohibited. Please supply a different email address."])

        base_data['email'] = 'foo@example.com'
        form = forms.RegistrationFormNoFreeEmail(data=base_data)
        self.failUnless(form.is_valid())
    

class DefaultRegistrationBackendTestCase(TestCase):
    """
    Test the default registration backend.

    Running these tests successfull will require two templates to be
    created for the sending of activation emails; details on these
    templates and their contexts may be found in the documentation for
    the default backend. The setting ``ACCOUNT_ACTIVATION_DAYS`` must
    also be specified, and must be an integer.
    
    """
    def setUp(self):
        """
        Create an instance of the default backend for use in testing.
        
        """
        from registration.backends.default import DefaultBackend
        self.backend = DefaultBackend()

    def test_registration(self):
        """
        Test the registration process: registration creates a new
        inactive account and a new profile with activation key,
        populates the correct account data and sends an activation
        email.
        
        """
        new_user = self.backend.register({}, 'bob', 'bob@example.com', 'secret')
        self.assertEqual(new_user.username, 'bob')
        self.failUnless(new_user.check_password('secret'))
        self.assertEqual(new_user.email, 'bob@example.com')
        self.failIf(new_user.is_active)
        self.assertEqual(RegistrationProfile.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_activation(self):
        """
        Test the activation process: activating within the permitted
        window sets the account's ``is_active`` field to ``True`` and
        resets the activation key, while failing to activate within
        the permitted window forbids later activation.
        
        """
        # First, test with a user activating inside the activation
        # window.
        valid_user = self.backend.register({}, 'alice', 'alice@example.com', 'swordfish')
        valid_profile = RegistrationProfile.objects.get(user=valid_user)
        activated = self.backend.activate({}, valid_profile.activation_key)
        self.assertEqual(activated.username, valid_user.username)
        self.failUnless(activated.is_active)

        # Fetch the profile again to verify its activation key has
        # been reset.
        valid_profile = RegistrationProfile.objects.get(user=valid_user)
        self.assertEqual(valid_profile.activation_key, RegistrationProfile.ACTIVATED)

        # Now test again, but with a user activating outside the
        # activation window.
        expired_user = self.backend.register({}, 'bob', 'bob@example.com', 'secret')
        expired_user.date_joined = expired_user.date_joined - datetime.timedelta(days=settings.ACCOUNT_ACTIVATION_DAYS)
        expired_user.save()
        expired_profile = RegistrationProfile.objects.get(user=expired_user)
        self.failIf(self.backend.activate({}, expired_profile.activation_key))
        self.failUnless(expired_profile.activation_key_expired())

    def test_allow(self):
        """
        Test that the setting ``REGISTRATION_OPEN`` appropriately
        controls whether registration is permitted.
        
        """
        self.failUnless(self.backend.registration_allowed({}))
        settings.REGISTRATION_OPEN = False
        self.failIf(self.backend.registration_allowed({}))

    def test_form_class(self):
        """
        Test that the default form class returned is
        ``registration.forms.RegistrationForm``.
        
        """
        self.failUnless(self.backend.get_form_class({}) is forms.RegistrationForm)

    def test_post_registration_redirect(self):
        """
        Test that the default post-registration redirect is the named
        pattern ``registration_complete``.
        
        """
        self.assertEqual(self.backend.post_registration_redirect({}, User()),
                         'registration_complete')
