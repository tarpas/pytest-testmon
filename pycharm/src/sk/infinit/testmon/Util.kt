package sk.infinit.testmon

import com.intellij.notification.Notification
import com.intellij.notification.NotificationType
import com.intellij.notification.Notifications
import java.lang.Exception

/**
 * Log error message to Notifications Bus.
 *
 * @param message - source message to log as Error message
 */
fun logErrorMessage(message: String) {
    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID, "Testmon message", message, NotificationType.INFORMATION))
}

/**
 * Log exception message to Notifications Bus.
 *
 * @param exception - source exception to log as Error message
 */
fun logErrorMessage(exception: Exception) {
    Notifications.Bus.notify(Notification(Notifications.SYSTEM_MESSAGES_GROUP_ID, "Testmon message", exception.message.toString(), NotificationType.INFORMATION))
}