from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect, resolve_url
from django.utils import timezone

from ..forms import AnswerForm
from ..models import Question, Answer


@login_required(login_url='common:login')
def answer_create(request, question_id):
    """
    Create an answer in arena
    """
    question = get_object_or_404(Question, pk=question_id)

    if request.method == "POST":
        form = AnswerForm(request.POST)
        if form.is_valid():
            answer = form.save(commit=False)
            answer.author = request.user
            answer.create_date = timezone.now()
            answer.question = question
            answer.save()

            messages.success(request, "Your answer has been posted.")

            return redirect(
                '{}#answer_{}'.format(
                    resolve_url('arena:detail', question_id=question.id),
                    answer.id
                )
            )
    else:
        form = AnswerForm()

    context = {
        'question': question,
        'form': form,
    }
    return render(request, 'arena/question_detail.html', context)


@login_required(login_url='common:login')
def answer_modify(request, answer_id):
    """
    Modify an existing answer
    """
    answer = get_object_or_404(Answer, pk=answer_id)

    if request.user != answer.author:
        messages.error(request, "You do not have permission to edit this answer.")
        return redirect('arena:detail', question_id=answer.question.id)

    if request.method == "POST":
        form = AnswerForm(request.POST, instance=answer)
        if form.is_valid():
            edited_answer = form.save(commit=False)
            edited_answer.modify_date = timezone.now()
            edited_answer.save()

            messages.success(request, "Your answer has been updated.")

            return redirect(
                '{}#answer_{}'.format(
                    resolve_url('arena:detail', question_id=answer.question.id),
                    answer.id
                )
            )
    else:
        form = AnswerForm(instance=answer)

    context = {
        'answer': answer,
        'form': form,
    }
    return render(request, 'arena/answer_form.html', context)


@login_required(login_url='common:login')
def answer_delete(request, answer_id):
    """
    Delete an existing answer
    """
    answer = get_object_or_404(Answer, pk=answer_id)
    question_id = answer.question.id

    if request.user != answer.author:
        messages.error(request, "You do not have permission to delete this answer.")
    else:
        answer.delete()
        messages.success(request, "Your answer has been deleted.")

    return redirect('arena:detail', question_id=question_id)


@login_required(login_url='common:login')
def answer_vote(request, answer_id):
    """
    Vote for an answer
    """
    answer = get_object_or_404(Answer, pk=answer_id)

    if request.user == answer.author:
        messages.error(request, "You cannot vote for your own answer.")
    else:
        answer.voter.add(request.user)
        messages.success(request, "Your vote has been recorded.")

    return redirect(
        '{}#answer_{}'.format(
            resolve_url('arena:detail', question_id=answer.question.id),
            answer.id
        )
    )