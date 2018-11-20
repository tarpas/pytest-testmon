package sk.infinit.testmon.extensions

import com.intellij.psi.PsiElement

/**
 * Contains information for draw red underline decoration on PsiElement.
 */
class RedUnderlineDecorationAnnotation(val message: String, val psiElement: PsiElement?)