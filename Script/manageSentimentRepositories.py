# -*- coding: utf-8 -*-

# Como executar o script
# python manageSentimentRepositories.py repositories.txt

import io
import os
import pymongo
import sys
import arrow
from datetime import datetime
from dateutil.parser import parse
import bson
from itertools import chain
import json
import re
import csv


def ler_arquivo(caminho):

    arq = open(caminho, 'r')
    texto = arq.readlines()
    arq.close()
    listaTexto = []

    for t in texto:
        listaTexto.append(t.replace('\n', ''))
		
    return listaTexto

repositories = ler_arquivo(sys.argv[1])

#####  Limpeza dos comentarios #####
url_regex = re.compile('[(]?http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\(\)\#,]|(?:%[0-9a-fA-F][0-9a-fA-F]))+[\)]?')
def remove_url(s):
    return url_regex.sub("url ",s)
	
codeShort_regex = re.compile(r'`.+`')	
def remove_codeShort(s, sep):
    vet = s.split(sep)
    t = ''
    i = 0

    while(i < len(vet)):
        if(i % 2 == 0):
            t += ' '
            t += vet[i]
        i += 1

    return t

comment_regex = re.compile('([\r\n\r\n])*>\s([\w]|[\d])*(.)*[.!?]*([\r\n\r\n])')
def remove_comment(s):
	return comment_regex.sub("",s)	
	
warning_regex = re.compile('([a-zA-Z]+\s[0-9]+[,]\s[0-9]+\s[0-9]+[:][0-9]+[:][0-9]+\s[aApPmM]+([\w]|[\d]|[.]|[_]|[\s])+[\n])*([A-Z])+(:)([a-zA-Z]|[.]|[0-9]|[\s]|[(]|[)]|[\[]|[\]]|[{]|[}])+(:)([a-zA-Z]|[.]|[0-9]|[\s]|[(]|[)]|[\[]|[\]]|[{]|[}])+[.]')
def remove_warning(s):
	return warning_regex.sub("",s)

exception_regex = re.compile('([\w]|[\d]|[.]|[_])+[\s]?[:]([\w]|[\d]|[.]|[_]|[\s])+[\']([\w]|[\d]|[.]|[_]|[\s])+[\']([\w]|[\d]|[.]|[_]|[\s]|[\(]|[\)]|[\$]|[\:])+[\)\n]')
def remove_exception(s):
	return exception_regex.sub("",s)
	
path_regex = re.compile('[\[]? ((([\w]|[...])([\:]|[\/])([\w]|[\d]|[\]|[\\]|[\/]|[/]|[\.]|[|]|[\-])+ )) [\]]?')
def remove_path(s):
	return path_regex.sub("",s)	

tag_regex = re.compile(r'<.*?>')	
def remove_tag(s):
	return tag_regex.sub("",s)	
	
href_regex = re.compile(r' href=".*?"')	
def remove_tag_href(s):
	return href_regex.sub("",s)	
	
table_regex = re.compile('(\|)([\|\s\-]|[\:arrow\_down\:]|[\:arrow\_up\:]|[❌]|[❓]|[✔️])+(\|)')	
def remove_table(s):
	return table_regex.sub("",s)
	
class_name_regex = re.compile('[...]?[a-zA-Z]+([\.]|[\/])([\w]|[\d]|[\_]|[\.]|[\/])+([a-zA-Z]|[0-9])+' )
def remove_class_name(s):
	return class_name_regex.sub("",s)	

def remove_code(s):
    vet = s.split('```')
    t = ''
    i = 0

    while(i < len(vet)):
        if(i % 2 == 0):
            t += ' '
            t += vet[i]
        i += 1

    return t
	
def preprocess_text(text):	

	text = remove_code(text)
	text = remove_tag(text)
	text = remove_tag_href(text)	
	text = remove_url(text)		
	text = remove_codeShort(text,'`')	
	text = remove_codeShort(text,'~~~')		
	text = remove_comment(text)	
	text = remove_warning(text)
	text = remove_exception(text)
	text = remove_class_name(text)
	text = remove_path(text)
	text = remove_table(text)
	text = text.replace('\t', ' ').replace('\r\r', ' ').replace('\r', ' ').replace('\n\n', ' ').replace('\n', '').replace('   ', ' ').replace('- ', '').replace('--', '')
	return  text


def printIssue(repository, number, status, type, creator, created_at, duration, msg):
	global f, sentAtual
	
	f.write(repository + "\t"+ number+"\t"+status + "\t" + type + "\t" + creator + "\t" + created_at + "\t" + duration)	
	if (sentAtual == 'Negative'): 
		f.write("\t+1" + "\t" + "\t"  + "\t" + str(msg) + "\n")
	if (sentAtual == 'Positive'): 
		f.write("\t" + "\t" + "\t+1"  + "\t" + str(msg) + "\n")
	if (sentAtual == 'Neutral'): 
		f.write("\t" + "\t+1" + "\t"  + "\t" + str(msg) + "\n")


import subprocess
import shlex

def run_command(command):
    p = subprocess.Popen(command,
                     stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT)
    return iter(p.stdout.readline, b'')

def removeCaracteres(c):
	a = ['b', '\\n', '\\r', "\'"]
	for i in a:
		c = c.replace(i, '')
	return c.split(' ')


####  Conta as polaridades dos comentarios e ####
def cont_polarity(polarity):
	global pos, neg, neut
	
	if (polarity < 0):
		neg = neg + 1
		
	elif (polarity > 0):
		pos = pos + 1
		
	elif (polarity == 0):
		neut = neut + 1	

		
#####
def sentiment(polarity):
	global sentAtual
	
	if (polarity < 0):
		sentAtual = "Negative"
		
	elif (polarity > 0):
		sentAtual = "Positive"		
		
	elif (polarity == 0):
		sentAtual = "Neutral"
		

##### Utilização da ferramenta de Análise de Sentimentos - SentiStrength  ###############
def sentiStrength(text):
	text = text.replace(' ', '+')
	out = ''

	#Exemplo: 'java -jar SentiStrengthCom.jar sentidata SentiStrength_Data/ text i+hate+you'
	command_sentiStrength = 'java -jar SentiStrengthCom.jar sentidata SentiStrength_Data/ text ' + text

	for output_line in run_command(command_sentiStrength):
		out += str(output_line)

	o = removeCaracteres(out)
	sentiment(int(o[0]) + int(o[1]))
	cont_polarity(int(o[0]) + int(o[1]))	


##### Apresentação dos resultados  ###
def printFileHeader():
	global f
	f.write("REPOSITORY" + "\tISSUE_ID" + "\tSTATUS" + "\tEVENT" + "\tUSER" + "\tCREATED_AT" + "\tTIME DURATION" + "\tNEGATIVE" + "\tNEUTRAL"+  "\tPOSITIVE"+ "\tMSG\n")


def printFileHeaderManage():
	global f2

	f2.write("REPOSITORY\t" + "\tISSUES REOPENED" + "\tISSUES WITH DISCUSSIONS" + "\tCOMMENTS"
	+ "\tQP1) Qt issues fechadas com sentimentos Positivos\t%"
	+ "\tQt issues fechadas com sentimentos Neutros\t%"
	+ "\tQt issues fechadas com sentimentos Negativos\t%"
	+ "\tQt issues reabertas com sentimentos Positivos\t%"
	+ "\tQt issues reabertas com sentimentos Neutros\t%"
	+ "\tQt issues reabertas com sentimentos Negativos\t%"
	+ "\tQP2) Qt issues que foram reabertas com sentimentos (Neutros + Negativos) > Positivos\t%"
	+ "\tQP2) Qt issues que foram reabertas com sentimentos (Neutros + Negativos) == Positivos\t%"
	+ "\tQP2) Qt issues que foram reabertas com sentimentos  Positivos > (Neutros + Negativos)\t%"
	+ "\tQP3) Qt issues que possuem sentimentos neutros entre fechamento e reabertura\t%"
	+ "\tQP3) Qt issues que possuem sentimentos negativos entre fechamento e reabertura\t%"
	+ "\tH4) Qt issues que foram fechadas com sentimentos Neutros > (Positivos + Negativos)\t%"
	+ "\tH4) Qt issues que foram fechadas com sentimentos Neutros == (Positivos + Negativos)\t%"
	+ "\tH4) Qt issues que foram fechadas com sentimentos (Positivos + Negativos) > Neutros\t%")
	

def printFileManage(qtIssues,qtIssuesWithDisc):
	global f2

	f2.write("\t" + str(qtIssues)+ "\t" + str(round(((qtIssues * 100)/qtIssuesWithDisc) , 2)) + "%")		

def printManageRepositories(repository, qt_issues, qt_issues_disc, qt_comments, issues_closed_positive, issues_closed_neutral, issues_closed_negative, issues_reopened_positive, issues_reopened_neutral, issues_reopened_negative, qt_neg_neut, qt_pos, qt_neut_closed_reopened, qt_neg_closed_reopened, qt_neut, qt_neg_pos, qt_neut_eq_neg_pos) :
	global f, f2
	
	print ("Projeto: ", repository, "\t Qt Issues Reabertas ", str(qt_issues), " Issues com discussões ", str(qt_issues_disc))
	f2.write("\n" + repository + "\t" +   str(qt_issues) + "\t" + str(qt_issues_disc))
	
	print ("Qt Comentários: ", str(qt_comments))
	f2.write("\t" + str(qt_comments))	
	
	print ("QP1) Qt issues fechadas com sentimentos Positivos: ", issues_closed_positive, "(", str((issues_closed_positive * 100)/qt_issues_disc) ,"%)")
	printFileManage(issues_closed_positive, qt_issues_disc)
	
	print ("Qt issues fechadas com sentimentos Neutros: ", issues_closed_neutral, "(", str((issues_closed_neutral * 100)/qt_issues_disc), "%)")
	printFileManage(issues_closed_neutral, qt_issues_disc)
	
	print ("Qt issues fechadas com sentimentos Negativos: ", issues_closed_negative, "(",str((issues_closed_negative * 100)/qt_issues_disc), "%)")
	printFileManage(issues_closed_negative, qt_issues_disc)
	
	print ("Qt issues reabertas com sentimentos Positivos: ", issues_reopened_positive, "(", str((issues_reopened_positive * 100)/qt_issues_disc), "%)")
	printFileManage(issues_reopened_positive, qt_issues_disc)
	
	print ("Qt issues reabertas com sentimentos Neutros: ", issues_reopened_neutral, "(", str((issues_reopened_neutral * 100)/qt_issues_disc), "%)")
	printFileManage(issues_reopened_neutral, qt_issues_disc)
	
	print ("Qt issues reabertas com sentimentos Negativos: ", issues_reopened_negative, "(", str((issues_reopened_negative * 100)/qt_issues_disc), "%)")
	printFileManage(issues_reopened_negative, qt_issues_disc)
	
	print ("QP2) Qt issues que foram reabertas com sentimentos (Neutros + Negativos) > Positivos : ", qt_neg_neut, "(", str((qt_neg_neut * 100)/qt_issues_disc), "%)")
	printFileManage(qt_neg_neut, qt_issues_disc)

	print ("QP2) Qt issues que foram reabertas com sentimentos (Neutros + Negativos) == Positivos: ", qt_neg_neut_eq_pos, "(", str((qt_neg_neut_eq_pos * 100)/qt_issues_disc), "%)")
	printFileManage(qt_neg_neut_eq_pos, qt_issues_disc)
	
	print ("QP2) Qt issues que foram reabertas com sentimentos  Positivos > (Neutros + Negativos) : ", qt_pos, "(", str((qt_pos * 100)/qt_issues_disc), "%)")
	printFileManage(qt_pos, qt_issues_disc)
	
	print ("QP3) Qt issues que possuem sentimentos neutros entre fechamento e reabertura : ", qt_neut_closed_reopened, "(", str((qt_neut_closed_reopened * 100)/qt_issues_disc), "%)")	
	printFileManage(qt_neut_closed_reopened,qt_issues_disc)
	
	print ("QP3) Qt issues que possuem sentimentos negativas entre fechamento e reabertura : ", qt_neg_closed_reopened, "(", str((qt_neg_closed_reopened * 100)/qt_issues_disc), "%)")		
	printFileManage(qt_neg_closed_reopened, qt_issues_disc)
	
	print ("Qt issues que foram fechadas com sentimentos Neutros > (Positivos + Negativos) : ", qt_neut, "(", str((qt_neut * 100)/qt_issues_disc), "%)")
	printFileManage(qt_neut, qt_issues_disc)

	print ("Qt issues que foram fechadas com sentimentos Neutros == (Positivos + Negativos) : ", qt_neut_eq_neg_pos, "(", str((qt_neut_eq_neg_pos * 100)/qt_issues_disc), "%)")
	printFileManage(qt_neut_eq_neg_pos, qt_issues_disc)	
	
	print ("Qt issues que foram fechadas com sentimentos (Positivos + Negativos) > Neutros : ", qt_neg_pos, "(", str((qt_neg_pos * 100)/qt_issues_disc), "%)")
	printFileManage(qt_neg_pos, qt_issues_disc)


##### Leitura dos repositorios no mongodb  ###############################
	
myclient = pymongo.MongoClient("mongodb://localhost:27017/")

mydb = myclient["collectedIssues_database"]
mycol = mydb["rm_issues"]

time_start = datetime.now()

for r in repositories:
    print ("\nRepositorio: ",r)

    f = open("timeline_rep_"+ r + "5.csv",'w')
    f2 = open("manage_repositories_"+ r +"5.csv",'w')
    printFileHeaderManage()
	
    mycol = mydb[r]
    issues = mycol.find({"Eventos.Evento" : "reopened" })

    qt_issues = mycol.count_documents({"Eventos.Evento" : "reopened"})	# Quantidade de issues reabertas
    qt_issues_disc = 0				## Quantidade de issues com discussoes
    qt_comments = 0 				## Quantidade total de comentarios
    printFileHeader()
    
    issues_closed_positive = 0  	## QP1) Quantidade de issues finalizadas com sentimento positive
	
    issues_closed_neutral = 0		## Quantidade de issues finalizadas com sentimento neutro
    issues_closed_negative = 0  	## Quantidade de issues finalizadas com sentimento negativo

    issues_reopened_positive = 0  	## Quantidade de issues reabertas com sentimento neutro
    issues_reopened_neutral = 0   	## Quantidade de issues reabertas com sentimento neutro
    issues_reopened_negative = 0  	## Quantidade de issues reabertas com sentimento neutro

    issues_closed_reopened = 0		## Issues que tiveram msgs entre o fechamento e reaberta
	
    qt_pos = 0						## QP2) Quantidade de issues com mensagens positivas antes de reabrir (Neg + Neut >= Pos)
    qt_neg_neut = 0					## QP2) Quantidade de issues com mensagens (Neg + Neut)  antes de reabrir (Neg + Neut >= Pos)
    qt_neg_neut_eq_pos = 0			## QP2) Quantidade de issues com mensagens (Neg + Neut)  antes de reabrir (Neg + Neut >= Pos)

    qt_neut_closed_reopened = 0		## QP3) Quantidade de issues com sentimentos neutros após fechar e antes de reabrir	
    qt_neg_closed_reopened  = 0		## QP3) Quantidade de issues com sentimentos negativos após fechar e antes de reabrir	
	
    qt_closed_reopened = 0			## Quantidade de issues que possuem msgs entre o fechamento e reaberta

    qt_neut = 0						## Quantidade de issues com msgs Neutras até ser fechada (Neut >  Neg+Pos)
    qt_neg_pos = 0					## Quantidade de issues com msgs (Negativas + Positivas) até ser fechada (Neut >  Neg+Pos)
    qt_neut_eq_neg_pos = 0			## Quantidade de issues com msgs (Negativas + Positivas) até ser fechada (Neut ==  Neg+Pos)

    issues = sorted(issues, key=lambda k: k['Criado em'])
	
    for i in issues:		
        
        comments = i["Comentários"]
        comentsNumber =  len(comments)
        sentAtual = "Neutral"
		
        clPosIssue = 0		# A issue atual foi fechada com sentimento positivo
        clNeuIssue = 0		# A issue atual foi fechada com sentimento neutro
        clNegIssue = 0		# A issue atual foi fechada com sentimento negativo
		
        clIssue = 0			# Sentiment quando a issue atual foi fechada
		
        reopNegIssue = 0	# A issue atual foi reaberta com sentimento negativo
        reopNeuIssue = 0	# A issue atual foi reaberta com sentimento neutro
        reopPosIssue = 0	# A issue atual foi reaberta com sentimento positivo
		
        reopIssue = 0		# Sentimento atual quando a issue foi
		
        clNegNeut = 0		# A issue atual possui (Neg + Neut) > (Pos)
        clNegNeutEqPos = 0	# A issue atual possui (Neg + Neut) == (Pos)		
        clPos = 0			# A issue atual possui (Neg + Neut) < (Pos)	

        clNeutReop = 0		# A issue atual possui msgs com sentimentos neutro após ser fechada e antes de ser reaberta
        clNegReop = 0		# A issue atual possui msgs com sentimentos neutro após ser fechada e antes de ser reaberta

        clNeut = 0			# A issue atual (Neut) >= (Neg + Pos)
        clNeutEqNegPos = 0	# A issue atual (Neut) >= (Neg + Pos)		
        clNegPos = 0		# A issue atual (Neut) >= (Neg + Pos)	
        closedIssue = 0
		
        if (comentsNumber > 1):

            qt_comments += comentsNumber
			
            f.write(r+ "\t" + str(i["id"])+"\t" + str(i["Situação"])+ "\topened" + "\t" + str(i["Autor"]) + "\t" + str(i["Criado em"]) + "\n")
            
            qt_issues_disc +=1			
            dt_cr = i["Criado em"]
            dt_ant = parse(str(i["Criado em"] ))
			
            comAt = 0	# comentario atual
            pos = 0		# quantidade de sentimentos positivos
            neg = 0		# quantidade de sentimentos negativos
            neut = 0	# quantidade de sentimentos neutros
			
			#### Title
            if (i["Título"] != ""):

                msg = str(preprocess_text(i["Título"]).encode('utf8'))
                sentiStrength(msg)
				
                printIssue(r,str(i["id"]), str(i["Situação"]),"title", str(i["Autor"]), str(i['Criado em']), "00:00", str(msg).encode('utf8'))
				
			### Body		
            if (bool(i["Descrição"]) != False) and (i["Descrição"] != ""):			

                msg = str(preprocess_text(i["Descrição"])).encode('utf8')			
                sentiStrength(str(msg))			
				
                printIssue(r,str(i["id"]), str(i["Situação"]),"body", str(i["Autor"]), str(i['Criado em']), "00:00", str(msg).encode('utf8'))
				

            comments = sorted(comments, key=lambda k: k['Data']) 
			
            events = i["Eventos"]
            events = sorted(events, key=lambda k: k['Criado em']) 

            event_ant = "opened"

            reopFirst = 0
			
            dt_issue_ant = dt_ant
			
            for e in events:
                if (e["Evento"] == "reopened") or (e["Evento"] == "closed") :			
                    dt_atual = parse(str(e["Criado em"]))


					#############################################################################
					#####  Verifica o ultimo sentimento antes da issue fechar é positivo    QP1)
                    if (e["Evento"] == "closed") and (sentAtual == "Positive") and (clIssue == 0):
                        issues_closed_positive +=1
                        clIssue = 1						
						
                    elif (e["Evento"] == "closed") and (sentAtual == "Neutral") and (clIssue == 0):
                        issues_closed_neutral +=1
                        clIssue = 1
					
                    elif (e["Evento"] == "closed") and (sentAtual == "Negative") and (clIssue == 0):
                        issues_closed_negative +=1
                        clIssue = 1						

					#############################################################################
					#####   Verifica se a quantidade de mensagens (Neg + Neut) > Pos quando a issue foi reaberta  QP2)
                    				
                    if (e["Evento"] == "reopened") and ((neg + neut) > pos) and (reopFirst == 0):					
                        clNegNeut = 1
                        reopFirst = 1
						
                    if (e["Evento"] == "reopened") and ((neg + neut) == pos) and (reopFirst == 0):					
                        clNegNeutEqPos = 1
                        reopFirst = 1
						
                    elif (e["Evento"] == "reopened") and (pos > (neg + neut)) and (reopFirst == 0):					
                        clPos = 1
                        reopFirst = 1						
						
					############################################################################	
					#####  Verifica se ultimo sentimento da issue antes de reabrir é neutro | negativo | positivo
					
                    if (e["Evento"] == "reopened") and (sentAtual == "Positive") and (reopIssue == 0):
                        issues_reopened_positive +=1
                        reopIssue = 1						

                    if (e["Evento"] == "reopened") and (sentAtual == "Neutral") and (reopIssue == 0):
                        issues_reopened_neutral +=1
                        reopIssue = 1
						
                    if (e["Evento"] == "reopened") and (sentAtual == "Negative") and (reopIssue == 0):
                        issues_reopened_negative +=1
                        reopIssue = 1						

					##### Verifica se a quantidade de mensagens (Neutras) >= ((Negativas + Positivas) quando a issue foi fechada
                    				
                    if (e["Evento"] == "closed") and (neut > (neg + pos)) and (closedIssue == 0):					
                        clNeut = 1         
                        closedIssue = 1				
                    elif (e["Evento"] == "closed") and (neut == (neg + pos))  and (closedIssue == 0):
                        clNeutEqNegPos = 1
                        closedIssue = 1
                    elif (e["Evento"] == "closed") and (neut < (neg + pos))  and (closedIssue == 0) :
                        clNegPos = 1
                        closedIssue = 1
						
                    qt_neut_cl_reop = 0
                    qt_neg_cl_reop = 0
					
                    for c in comments:
                        dt_issue = parse(str(c["Data"]))
                        if ( dt_ant < dt_issue ) and ( dt_issue <= dt_atual) :
                            comAt +=1		
                            if (c['Comentário'] != ""):
                                msg = str(preprocess_text(c['Comentário']).encode("utf-8"))
                                sentiStrength(msg)								
                                printIssue(r,str(i["id"]), str(i["Situação"]),str(comAt), str(c["Autor"]), str(i['Criado em']),str( round( (dt_issue - dt_issue_ant).seconds/60, 2)), str(msg).encode('utf8'))	

						#######################
						##### QP3  Mensagens com sentimentos Neutro entre o fechamento e reaberta indica que a issue vai ser reaberta ou tudo ok não interfere
                                if (e["Evento"] == "reopened") and (event_ant == "closed"):
                                    issues_closed_reopened = 1
									
                                if (e["Evento"] == "reopened") and (event_ant == "closed") and (sentAtual == "Neutral") :
                                    clNeutReop = 1								
                                    qt_neut_cl_reop += 1
									
                                elif (e["Evento"] == "reopened") and (event_ant == "closed") and (sentAtual == "Negative") :
                                    clNegReop = 1								
                                    qt_neg_cl_reop += 1	
									
                            dt_issue_ant = dt_issue
							
                    f.write(r+ "\t" +str(i["id"]) + "\t" + str(i["Situação"]) + "\t"+ str(e["Evento"]) + "\t - \t" + str(e["Criado em"]) + "\t" 
					+ str( round( (dt_atual - dt_ant).seconds/60, 2))  + "\t" + str(neg) + "\t" + str(neut) + "\t" + str(pos) + "\n")															
							
                    event_ant = e["Evento"]
                    dt_ant = dt_atual


			# Discussões de issue apos o fechamento da issue ou quando a issue continua reaberta            			
            if ((dt_ant > parse(str(i["Criado em"] ))) or (str(i["Situação"] ) == 'open')):
                
                for c in comments:
                    dt_issue = parse(str(c["Data"]))
                    if (dt_issue > dt_ant):
                        comAt +=1	
                        msg = str(preprocess_text(c['Comentário']).encode("utf-8"))                 						
                        sentiStrength(msg)
                        printIssue(r,str(i["id"]), str(i["Situação"]),str(comAt), str(c["Autor"]), str(i['Criado em']), str( round( (dt_issue - dt_issue_ant).seconds/60, 2)), str(msg).encode('utf8'))				
					
            f.write(r+"\t"+str(i["id"]) + "\t" + str(i["Situação"]) + "\t-"+ "\t-" + "\t-\t-\t" + str(neg) + "\t" + str(neut) + "\t" + str(pos) + "\n")
			
        qt_pos += clPos							## QP2)	Quantidade de issues que possuem msgs positivas  para responder se (Neg + Neut) < Pos quando uma issue é fechada		
        qt_neg_neut += clNegNeut				## QP2)	Quantidade de issues que possuem msgs (negativas + neutras)  para responder se (Neg + Neut) > Pos quando uma issue é fechada		
        qt_neg_neut_eq_pos += clNegNeutEqPos	## QP2)	Quantidade de issues que possuem msgs (negativas + neutras)  para responder se (Neg + Neut) == Pos quando uma issue é fechada		

        qt_neut_closed_reopened += clNeutReop	# QP3) quantidade de issues fechadas com msgs Neutras antes de reabertura 	
        qt_neg_closed_reopened += clNegReop		# QP3) Quantidade de issues fechadas com msgs Negativas antes de reabertura 
		
        qt_closed_reopened += issues_closed_reopened		# QP3) Quantidade de issues fechadas com msgs Negativas antes de reabertura 
		
        qt_neg_pos += clNegPos					## Quantidade de issues que possuem msgs (Negativas + Positivas) > Neut  quando a issue é fechada
        qt_neut += clNeut						## Quantidade de issues que possuem msgs Neutras > (Neg + Pos) quando a issue é fechada
        qt_neut_eq_neg_pos += clNeutEqNegPos	## Quantidade de issues que possuem msgs Neutras == (Neg + Pos) quando a issue é fechada
        
    if (qt_issues_disc > 0) :
        printManageRepositories(r, qt_issues, qt_issues_disc, qt_comments, issues_closed_positive, issues_closed_neutral, issues_closed_negative, issues_reopened_positive, issues_reopened_neutral, issues_reopened_negative, qt_neg_neut, qt_pos, qt_neut_closed_reopened, qt_neg_closed_reopened, qt_neut, qt_neg_pos, qt_neut_eq_neg_pos) 
    else:
        print("Projeto:  ", r, "Qt Issues Reabertas", str(qt_issues) , "Issues com discussões  ", str(qt_issues))		
    f.close()	
    f2.close()	

time_end = datetime.now()
print("Inicio: ",  str(time_start) , " - fim : ", time_end, " duração : ", str(time_end - time_start).replace('\t', ',')  , " (",str( round( (time_end - time_start).seconds/60, 2)) , "minutos)")

