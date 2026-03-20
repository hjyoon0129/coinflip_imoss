from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.utils import timezone

from ..forms import QuestionForm
from ..models import Question


@login_required(login_url='common:login')
def question_create(request):
    """
    Create a new question
    """
    if request.method == 'POST':
        form = QuestionForm(request.POST, request.FILES)
        if form.is_valid():
            question = form.save(commit=False)
            question.author = request.user
            question.create_date = timezone.now()
            question.save()
            form.save_m2m()

            messages.success(request, "Your post has been created.")
            return redirect('arena:index')
    else:
        form = QuestionForm()

    context = {'form': form}
    return render(request, 'arena/question_form.html', context)


@login_required(login_url='common:login')
def question_modify(request, question_id):
    """
    Modify an existing question
    """
    question = get_object_or_404(Question, pk=question_id)

    if request.user != question.author:
        messages.error(request, "You do not have permission to edit this post.")
        return redirect('arena:detail', question_id=question.id)

    if request.method == "POST":
        form = QuestionForm(request.POST, request.FILES, instance=question)
        if form.is_valid():
            edited_question = form.save(commit=False)
            edited_question.modify_date = timezone.now()
            edited_question.save()
            form.save_m2m()

            messages.success(request, "Your post has been updated.")
            return redirect('arena:detail', question_id=edited_question.id)
    else:
        form = QuestionForm(instance=question)

    context = {'form': form, 'question': question}
    return render(request, 'arena/question_form.html', context)


@login_required(login_url='common:login')
def question_delete(request, question_id):
    """
    Delete an existing question
    """
    question = get_object_or_404(Question, pk=question_id)

    if request.user != question.author:
        messages.error(request, "You do not have permission to delete this post.")
        return redirect('arena:detail', question_id=question.id)

    question.delete()
    messages.success(request, "Your post has been deleted.")
    return redirect('arena:index')


@login_required(login_url='common:login')
def question_vote(request, question_id):
    """
    Vote for a question
    """
    question = get_object_or_404(Question, pk=question_id)

    if request.user == question.author:
        messages.error(request, "You cannot vote for your own post.")
    else:
        question.voter.add(request.user)
        messages.success(request, "Your vote has been recorded.")

    return redirect('arena:detail', question_id=question.id)