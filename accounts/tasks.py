from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives


@shared_task
def send_activation_email(recipient_email, activation_link):
    """
    Asynchronous task to send account activation email.
    """
    subject = "Activate Your Account 🚀"
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [recipient_email]

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; margin:0; padding:0;">
        <table width="100%" cellpadding="0" cellspacing="0">
          <tr>
            <td align="center">
              <table width="600" cellpadding="20" cellspacing="0" 
                     style="max-width:600px; border:1px solid #ddd; border-radius:10px; background-color:#f9f9f9;">
                <tr>
                  <td align="left" style="text-align:left;">
                    <h2 style="color:#007BFF; margin-bottom:20px;">Welcome</h2>
                    <p>Hello!</p>
                    <p>To start using your account, please activate it by clicking the button below:</p>

                    <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin:20px auto;">
                      <tr>
                        <td bgcolor="#007BFF" style="border-radius:5px; text-align:center;">
                          <a href="{activation_link}" target="_blank" 
                             style="display:inline-block; padding:12px 25px; font-size:16px; font-weight:bold;
                                    color:#ffffff; text-decoration:none; border-radius:5px; font-family: Arial, sans-serif;">
                            Activate Account
                          </a>
                        </td>
                      </tr>
                    </table>
                    <p style="margin-top:30px;">Best regards</p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
        </table>
      </body>
    </html>
    """

    msg = EmailMultiAlternatives(subject, "", from_email, to)
    msg.attach_alternative(html_content, "text/html")
    msg.send()


@shared_task
def send_reset_email(email, username, reset_link):
    """
    Asynchronous task to send password reset email.
    """
    subject = "Reset Your Password"
    from_email = settings.DEFAULT_FROM_EMAIL
    to = [email]

    html_content = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <p>Hello {username},</p>
        <p>To reset your password, click the button below:</p>
        <table role="presentation" cellspacing="0" cellpadding="0">
          <tr>
            <td align="center" bgcolor="#007BFF" style="border-radius:5px;">
              <a href="{reset_link}" target="_blank" 
                 style="display:inline-block; padding:12px 25px; font-size:16px; font-weight:bold;
                        color:#ffffff; text-decoration:none; border-radius:5px;">
                Reset Password
              </a>
            </td>
          </tr>
        </table>
        <p style="margin-top:20px;">If you did not request this, please ignore this email.</p>
      </body>
    </html>
    """

    msg = EmailMultiAlternatives(subject, "", from_email, to)
    msg.attach_alternative(html_content, "text/html")
    msg.send()


@shared_task
def send_verification_email(to_email, code):
    """
    Asynchronous task to send two-step verification code.
    """
    subject = "Your Verification Code"
    # Unified using settings for consistent sender identity
    from_email = settings.DEFAULT_FROM_EMAIL
    text_content = f"Your verification code is: {code}"

    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h2 style="color: #333;">Two-Step Verification</h2>
        <p>Use the following code to verify your account:</p>
        <p style="font-size: 24px; font-weight: bold; color: #2d6cdf; background-color: #f1f5fb; padding: 10px; display: inline-block; border-radius: 5px;">
            {code}
        </p>
        <p style="color: #555; margin-top: 20px;">This code will expire in 2 minutes.</p>
        <hr>
        <p style="font-size: 12px; color: #999;">If you did not request this code, please ignore this email.</p>
    </body>
    </html>
    """

    msg = EmailMultiAlternatives(subject, text_content, from_email, [to_email])
    msg.attach_alternative(html_content, "text/html")
    msg.send()
